"""Reusable FastAPI authentication dependency and authorization checks.

设计约束（改动前请先读这段）：

1. **认证**只提供 `get_current_user` 一个依赖；**授权**一律在端点函数体内显式调用
   `ensure_self` / `ensure_can_read_user`。**不要**把依赖挂到 `APIRouter(...)` 或
   `include_router(..., dependencies=[...])` 上 —— 前端有多个页面在未登录时就会打这些接口
   （`/kb/knowledge-graph`、`/api/health`、`/api/practice/*`），挂全局依赖等于一次打断所有人。

2. **`role` 不能作为跨用户读取的依据。** `POST /api/auth/register` 的请求体里
   `role: Literal["student", "teacher"]`（backend/auth/models.py）由客户端自填，
   `register_user` 也只校验枚举（backend/auth/service.py），不做任何身份核验 ——
   任何人注册时填 `"role": "teacher"` 在数据库里就是教师。

   **教师审批（2026-09-14 加）改变了后果，但没有改变本条结论**：自封 teacher 的人
   注册后 `teacher_status='pending'`，`require_teacher` 会把他挡在教师端点外。
   但这个字段**只挡教师端点**，`can_read_user` 的判据里没有它 —— 一个 pending 教师
   只要真的把学生招进了自己的班，就照样能读该班学情。这是有意的（班级归属是真实关系），
   所以下面的四条仍然是唯一的跨用户读取依据。

   跨用户读取只认这四件事：
     (1) 本人
     (2) 数据库里的 admin —— **唯一不可自封的角色**：
         RegisterRequest 的 Literal 只允许 student|teacher（admin 会被 422 拒绝），
         而 users 表的 CHECK 约束才含 admin，所以 admin 只能由数据库写入
     (3) 真实班级归属：目标学生的 class_id 指向的班级，其 teacher_id 就是调用者
     (4) 已批准的共享申请 share_requests

   注意 (3) 不会因为自封 teacher 而失守：自封者可以建班，但没法把别人的学生挪进自己的班
   —— join_class 需要学生本人输入邀请码，这与平台既有信任模型一致
   （学生输邀请码 = 同意该老师看自己的班级数据）。
"""

from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# ⚠️ 只允许在模块级导入 `backend.auth.models` —— 两个 `__init__.py` 都会急切导入自己的 router
# （`backend/auth/__init__.py:3`、`backend/learning/__init__.py:4`），因此存在一个真实的导入环：
#     backend.auth.service → backend.learning.database → backend.learning.__init__
#       → backend.learning.router → backend.auth.dependencies
# 只要从 `backend.kb.structured`（它被 backend.grading.knowledge 导入）这类较早的位置进入，
# `backend.auth.service` 就还停在 `service.py:14`，此处模块级导入它会直接 ImportError。
# `AuthUser` 必须留在模块级：FastAPI 用 `get_type_hints` 在模块 globals 里解析注解，
# 移到函数内会让路由注册时 NameError。其余两个改成函数内导入即可断环。
from backend.auth.models import AuthUser

# 与 backend/auth/router.py:11 的 bearer_scheme 等价。
# 那边是线上唯一在跑的鉴权代码，保持不动，两个实例互不影响。
bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "需要 Bearer token") -> HTTPException:
    return HTTPException(
        status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthUser:
    """认证：解析 `Authorization: Bearer <token>`，返回 AuthUser（role 取自数据库）。"""
    from backend.auth.service import AuthError, get_user_from_token  # 见文件头：断环

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        return get_user_from_token(credentials.credentials)
    except AuthError as exc:
        # 与 backend/auth/router.py:_raise_http 的映射保持一致
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        raise HTTPException(
            status_code=exc.status_code, detail=str(exc), headers=headers
        ) from exc


# --------------------------------------------------------------------------
# 授权：在端点函数体内显式调用
# --------------------------------------------------------------------------


def ensure_self(user: AuthUser, target_user_id: int) -> None:
    """写路径：只能写自己。

    连 admin 也不代写 —— 写操作保持最小权限、可审计。
    """
    if target_user_id != user.user_id:
        raise HTTPException(status_code=403, detail="只能操作当前登录用户自己的数据")


def _is_class_teacher_of(teacher_id: int, student_id: int) -> bool:
    """调用者是否是目标学生所在班级的老师。

    只看 classes.teacher_id，**不看 role 字段**（role 可自封，见模块 docstring）。
    """
    from backend.learning.database import connection_scope  # 见文件头：断环

    with connection_scope() as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM users AS student
            JOIN classes AS c ON c.id = student.class_id
            WHERE student.id = ? AND c.teacher_id = ?
            LIMIT 1
            """,
            (student_id, teacher_id),
        ).fetchone()
    return row is not None


def _has_approved_share(requester_id: int, target_user_id: int) -> bool:
    """是否已有被批准的共享申请。

    方向与 backend/management/share_service.py:get_shared_report 保持一致：
    requester_id 是查看者，target_user_id 是数据所有者。
    """
    from backend.learning.database import connection_scope  # 见文件头：断环

    with connection_scope() as connection:
        row = connection.execute(
            """
            SELECT 1 FROM share_requests
            WHERE requester_id = ? AND target_user_id = ? AND status = 'approved'
            LIMIT 1
            """,
            (requester_id, target_user_id),
        ).fetchone()
    return row is not None


def can_read_user(user: AuthUser, target_user_id: int) -> bool:
    """能否读取 target_user_id 的学情数据。"""
    if target_user_id == user.user_id:
        return True
    if user.role == "admin":
        return True
    if _is_class_teacher_of(user.user_id, target_user_id):
        return True
    if _has_approved_share(user.user_id, target_user_id):
        return True
    return False


def ensure_can_read_user(user: AuthUser, target_user_id: int) -> None:
    """读路径：本人 / admin / 真实班级归属 / 已批准共享，否则 403。"""
    if not can_read_user(user, target_user_id):
        raise HTTPException(status_code=403, detail="只能查看自己的学情数据")


def require_teacher(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    """教师端点：必须是已批准的教师（或 admin）。

    用 **403 不是 401**：本项目 401 的语义是「凭证失效，去重新登录」（还带
    WWW-Authenticate 头，前端会清登录态），而这里是**已认证但未授权**。
    前端的 fetchApiJson 会把 detail 原文贴到面板上，所以这些文案就是给用户看的，
    可以具体到「待审批」/「未通过」。
    """
    # 顺序有讲究：先放行 admin，再给 pending / rejected 各自的文案，
    # 最后才是笼统的「不是教师」—— 否则待审批教师只会看到一句没头没脑的"需要教师权限"。
    if user.role == "admin":
        return user
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="需要教师权限")
    if user.teacher_status == "pending":
        raise HTTPException(
            status_code=403,
            detail="教师账号待管理员审批，审批通过后才能使用教师功能",
        )
    if user.teacher_status == "rejected":
        raise HTTPException(
            status_code=403,
            detail="教师账号申请未通过审批，无法使用教师功能",
        )
    return user


def resolve_actor(user: AuthUser, claimed_id: int | None, *, what: str = "操作者") -> int:
    """把「请求里自报的身份」与「token 里的身份」对齐，返回可信的 user_id。

    旧客户端仍在传 teacher_id / requester_id，所以参数保留为可选（不传就用 token 的身份）；
    但**传了就必须一致**，不一致直接 403。

    不静默忽略的理由：静默忽略会把客户端的串号 bug 藏起来 —— 一个把 A 的 id 传给 B 的
    token 的客户端会「看起来正常但数据写到了 A 名下」。而串号恰恰是最该立刻暴露的情况。
    """
    if claimed_id is None:
        return user.user_id
    if claimed_id != user.user_id:
        raise HTTPException(status_code=403, detail=f"{what}与当前登录用户不一致")
    return user.user_id


def require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    """破坏性操作的唯一可信门槛。

    admin 无法通过 /api/auth/register 自封（Literal 只允许 student|teacher），
    因此这是全系统唯一可信的角色判定。

    超管的 role 由 backend/auth/service.py:_user_from_row 按 .env 的
    SUPER_ADMIN_USERNAME 提升而来，落到这里同样是 "admin"，所以本函数不用改。
    """
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
