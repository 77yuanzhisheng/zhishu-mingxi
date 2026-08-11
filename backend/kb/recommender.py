"""
个性化推荐引擎
===============

基于知识图谱 node_id 和用户掌握度，提供：
1. 个性化题目推荐（按薄弱点 + 难度梯度出题）
2. 学习路径推荐（按依赖拓扑排序）

数据来源：题库节点映射.md（每道题标记 node_id + 类型 + 难度）
"""

import os
import re
import logging
from typing import List, Dict, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# 知识图谱模块间依赖关系（从 router.py 同步）
MODULE_DEPENDENCIES = {
    "propositional_logic": [],
    "predicate_logic": ["propositional_logic"],
    "set_theory": ["propositional_logic"],
    "induction": ["propositional_logic"],
    "relations": ["set_theory", "predicate_logic"],
    "graph_theory": ["relations", "set_theory"],
}

# node_id 前缀到模块的映射
NODE_MODULE_MAP = {
    "pl": "propositional_logic",
    "fl": "predicate_logic",
    "st": "set_theory",
    "mi": "induction",
    "rel": "relations",
    "gt": "graph_theory",
}


class QuestionRecommender:
    """
    题目推荐器。

    用法:
        rec = QuestionRecommender()
        questions = rec.recommend(node_id="pl_02_02", level=2, count=5)
    """

    def __init__(self, mapping_file: Optional[str] = None):
        self.mapping_file = mapping_file or "data/documents/题库节点映射.md"
        self.questions: List[Dict] = []
        self.by_node: Dict[str, List[Dict]] = defaultdict(list)
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._load_mapping()
        self._loaded = True

    def _load_mapping(self):
        """从映射文件加载题库"""
        if not os.path.exists(self.mapping_file):
            logger.warning(f"题库映射文件不存在: {self.mapping_file}")
            return

        with open(self.mapping_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("##"):
                    continue
                # 格式: node_id: xxx | 类型: xxx | 题目: xxx | 难度: n
                fields = {}
                for part in line.split("|"):
                    part = part.strip()
                    if ":" in part:
                        key, _, value = part.partition(":")
                        fields[key.strip()] = value.strip()

                if "node_id" in fields and "题目" in fields:
                    q = {
                        "node_id": fields["node_id"],
                        "type": fields.get("类型", "概念题"),
                        "content": fields["题目"],
                        "difficulty": int(fields.get("难度", 3)),
                    }
                    self.questions.append(q)
                    self.by_node[fields["node_id"]].append(q)

        logger.info(f"加载题库映射: {len(self.questions)} 道题, "
                     f"{len(self.by_node)} 个知识点")

    def recommend(
        self,
        node_id: str,
        level: int = 2,
        count: int = 5,
    ) -> List[Dict]:
        """
        根据薄弱知识点和当前掌握等级推荐题目。

        参数:
            node_id: 薄弱知识点的 node_id
            level: 当前掌握等级 (0-4)
            count: 需要返回的题目数

        逻辑:
            - 优先出 level+1 难度的题（挑战区）
            - 数量不足时补充 level 难度的题（巩固区）
            - 还不够时补充 level-1 难度的题（基础区）
            - 难度范围 1-5
        """
        self._ensure_loaded()

        candidates = self.by_node.get(node_id, [])
        if not candidates:
            return []

        # 按难度分组
        by_diff = defaultdict(list)
        for q in candidates:
            by_diff[q["difficulty"]].append(q)

        # 推荐策略
        target_diff = min(level + 1, 5)  # 当前等级+1 = 挑战难度
        result = []

        # 第一轮：挑战难度
        result.extend(by_diff.get(target_diff, [])[:count])

        # 第二轮：当前难度（巩固）
        if len(result) < count:
            result.extend(by_diff.get(level, [])[:count - len(result)])

        # 第三轮：基础难度
        if len(result) < count:
            for d in range(max(1, level - 1), 0, -1):
                result.extend(by_diff.get(d, [])[:count - len(result)])
                if len(result) >= count:
                    break

        # 第四轮：任何难度
        if len(result) < count:
            for d in range(1, 6):
                if d not in [target_diff, level, level - 1]:
                    extra = by_diff.get(d, [])
                    result.extend(extra[:count - len(result)])
                    if len(result) >= count:
                        break

        return result[:count]

    def recommend_by_nodes(
        self,
        weak_nodes: List[str],
        levels: Optional[Dict[str, int]] = None,
        count_per_node: int = 3,
    ) -> Dict[str, List[Dict]]:
        """
        批量推荐：对多个薄弱节点各推荐题目。

        返回: {node_id: [questions]}
        """
        self._ensure_loaded()
        levels = levels or {}

        result = {}
        for node_id in weak_nodes:
            level = levels.get(node_id, 2)
            qs = self.recommend(node_id, level, count_per_node)
            if qs:
                result[node_id] = qs
        return result

    def recommend_learning_path(
        self,
        weak_nodes: List[str],
        user_levels: Optional[Dict[str, int]] = None,
    ) -> List[Dict]:
        """
        根据薄弱节点和知识图谱依赖关系，推荐学习路径。

        原理：
        1. 找到 weak_nodes 涉及的所有模块
        2. 按模块依赖拓扑排序（先在依赖的模块上打好基础）
        3. 在每个薄弱节点上，按"基础→进阶→综合"排列题目
        """
        self._ensure_loaded()
        user_levels = user_levels or {}

        # 收集薄弱节点涉及的模块
        modules_involved = set()
        for nid in weak_nodes:
            prefix = nid.split("_")[0] if "_" in nid else nid[:2]
            mod = NODE_MODULE_MAP.get(prefix)
            if mod:
                modules_involved.add(mod)

        # 拓扑排序模块
        sorted_modules = self._topo_sort(modules_involved)

        # 按排序后的模块顺序，构建学习路径
        path = []
        step = 0
        for mod in sorted_modules:
            # 找出该模块下的薄弱节点
            mod_weak_nodes = [
                nid for nid in weak_nodes
                if NODE_MODULE_MAP.get(nid.split("_")[0] if "_" in nid else nid[:2]) == mod
            ]

            for nid in mod_weak_nodes:
                level = user_levels.get(nid, 2)
                questions = self.recommend(nid, level, count=3)

                # 获取节点名称（从映射中推断）
                node_name = self._get_node_name(nid)

                step += 1
                path.append({
                    "step": step,
                    "module": mod,
                    "node_id": nid,
                    "node_name": node_name,
                    "current_level": level,
                    "reason": f"模块「{mod}」下的薄弱知识点，当前等级{level}，"
                              f"优先出难度{min(level+1,5)}的题目",
                    "questions": questions,
                })

        return path

    def _topo_sort(self, modules: set) -> List[str]:
        """对涉及的模块做拓扑排序，被依赖的在前"""
        visited = set()
        result = []

        def dfs(m):
            if m in visited or m not in MODULE_DEPENDENCIES:
                return
            visited.add(m)
            for dep in MODULE_DEPENDENCIES.get(m, []):
                if dep in modules:
                    dfs(dep)
            result.append(m)

        for m in sorted(modules):
            dfs(m)

        # 也包含被依赖但不在 weak 模块中的基础模块
        for m in sorted(modules):
            for dep in MODULE_DEPENDENCIES.get(m, []):
                if dep not in modules and dep not in visited:
                    result.insert(0, dep)
                    visited.add(dep)

        return result

    def _get_node_name(self, node_id: str) -> str:
        """从映射文件中查找节点名称"""
        self._ensure_loaded()
        # 尝试从已有的题目中推断节点名称
        for q in self.questions:
            if q["node_id"] == node_id:
                # 从题目内容截取关键概念
                return q["content"][:40]
        return node_id


# 全局单例
_recommender: Optional[QuestionRecommender] = None


def get_recommender() -> QuestionRecommender:
    global _recommender
    if _recommender is None:
        _recommender = QuestionRecommender()
    return _recommender
