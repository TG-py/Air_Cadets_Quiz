"""Route table for the API feature modules."""
import re

from api_auth import (
    api_me, api_login, api_logout, api_change_password, api_next_question,
    api_record_attempt, api_finish_quiz_session,
)
from api_questions import (
    api_topics, api_question_counts, api_list_questions, api_question_board,
    api_set_question_board_state, api_submit_question, api_pending, api_review,
    api_delete_question, api_archive_question, api_restore_question,
    api_list_stale, api_set_stale, api_set_needs_review, api_accept_ai_question,
    api_reject_ai_question, api_send_ai_to_human, api_apply_question_updates,
    api_apply_combined_review, api_report_question,
)
from api_practice import (
    api_practice_start, api_practice_next, api_practice_attempt,
    api_practice_finish, api_list_practice_sessions, api_get_practice_session,
    api_delete_practice_session,
)
from api_issues import (
    api_submit_website_issue, api_list_website_issues, api_resolve_website_issue,
)
from api_admin import (
    api_list_reports, api_resolve_report, api_stats, api_progress_trends,
    api_list_users, api_create_user, api_set_user_active, api_set_user_username,
    api_set_user_password, api_reset_progress, api_list_quiz_sessions,
    api_get_quiz_session, api_delete_quiz_session, api_edit_question,
    api_rename_topic, import_questions, api_delete_all_questions,
)

ROUTES = [
    ("GET", r"^/api/auth/me$", api_me, "open"),
    ("POST", r"^/api/auth/login$", api_login, "csrf"),
    ("POST", r"^/api/auth/logout$", api_logout, "csrf"),
    ("POST", r"^/api/auth/change-password$", api_change_password, "staff"),
    ("GET", r"^/api/quiz/next$", api_next_question, "staff"),
    ("POST", r"^/api/attempts$", api_record_attempt, "staff"),
    ("POST", r"^/api/quiz/finish$", api_finish_quiz_session, "staff"),
    ("GET", r"^/api/questions$", api_list_questions, "staff"),
    ("GET", r"^/api/questions/counts$", api_question_counts, "open"),
    ("GET", r"^/api/admin/question-board$", api_question_board, "admin"),
    ("POST", r"^/api/admin/questions/(?P<id>\d+)/board-state$", api_set_question_board_state, "admin"),
    ("GET", r"^/api/topics$", api_topics, "open"),
    ("POST", r"^/api/questions$", api_submit_question, "csrf"),
    ("GET", r"^/api/admin/pending$", api_pending, "admin"),
    ("POST", r"^/api/admin/questions/(?P<id>\d+)/(?P<status>approve|reject)$", api_review, "admin"),
    ("POST", r"^/api/admin/questions/(?P<id>\d+)/delete$", api_delete_question, "admin"),
    ("POST", r"^/api/admin/questions/(?P<id>\d+)/archive$", api_archive_question, "admin"),
    ("POST", r"^/api/admin/questions/(?P<id>\d+)/restore$", api_restore_question, "admin"),
    ("GET", r"^/api/admin/stale$", api_list_stale, "admin"),
    ("POST", r"^/api/admin/questions/(?P<id>\d+)/stale$", api_set_stale, "admin"),
    ("POST", r"^/api/admin/questions/(?P<id>\d+)/needs-review$", api_set_needs_review, "admin"),
    ("POST", r"^/api/admin/questions/(?P<id>\d+)/accept-ai$", api_accept_ai_question, "admin"),
    ("POST", r"^/api/admin/questions/(?P<id>\d+)/reject-ai$", api_reject_ai_question, "admin"),
    ("POST", r"^/api/admin/questions/(?P<id>\d+)/send-to-human$", api_send_ai_to_human, "admin"),
    ("POST", r"^/api/admin/question-updates$", api_apply_question_updates, "admin"),
    ("POST", r"^/api/admin/question-check-review$", api_apply_combined_review, "admin"),
    ("POST", r"^/api/questions/(?P<id>\d+)/report$", api_report_question, "csrf"),
    ("POST", r"^/api/website-issues$", api_submit_website_issue, "csrf"),
    ("GET", r"^/api/admin/website-issues$", api_list_website_issues, "admin"),
    ("POST", r"^/api/admin/website-issues/(?P<id>\d+)/resolve$", api_resolve_website_issue, "admin"),
    ("POST", r"^/api/practice/start$", api_practice_start, "csrf"),
    ("GET", r"^/api/practice/next$", api_practice_next, "open"),
    ("POST", r"^/api/practice/attempts$", api_practice_attempt, "csrf"),
    ("POST", r"^/api/practice/finish$", api_practice_finish, "csrf"),
    ("GET", r"^/api/admin/reports$", api_list_reports, "admin"),
    ("POST", r"^/api/admin/reports/(?P<id>\d+)/resolve$", api_resolve_report, "admin"),
    ("POST", r"^/api/admin/questions/(?P<id>\d+)/edit$", api_edit_question, "admin"),
    ("POST", r"^/api/admin/import$", import_questions, "admin"),
    ("POST", r"^/api/admin/questions/delete-all$", api_delete_all_questions, "admin"),
    ("GET", r"^/api/admin/users$", api_list_users, "admin"),
    ("POST", r"^/api/admin/users$", api_create_user, "admin"),
    ("POST", r"^/api/admin/users/(?P<id>\d+)/active$", api_set_user_active, "admin"),
    ("POST", r"^/api/admin/users/(?P<id>\d+)/username$", api_set_user_username, "admin"),
    ("POST", r"^/api/admin/users/(?P<id>\d+)/password$", api_set_user_password, "admin"),
    ("POST", r"^/api/admin/topics/rename$", api_rename_topic, "admin"),
    ("POST", r"^/api/admin/reset-progress$", api_reset_progress, "admin"),
    ("GET", r"^/api/admin/quiz-sessions$", api_list_quiz_sessions, "admin"),
    ("GET", r"^/api/admin/quiz-sessions/(?P<id>\d+)$", api_get_quiz_session, "admin"),
    ("POST", r"^/api/admin/quiz-sessions/(?P<id>\d+)/delete$", api_delete_quiz_session, "admin"),
    ("GET", r"^/api/admin/practice-sessions$", api_list_practice_sessions, "admin"),
    ("GET", r"^/api/admin/practice-sessions/(?P<id>\d+)$", api_get_practice_session, "admin"),
    ("POST", r"^/api/admin/practice-sessions/(?P<id>\d+)/delete$", api_delete_practice_session, "admin"),
    ("GET", r"^/api/stats$", api_stats, "staff"),
    ("GET", r"^/api/admin/progress-trends$", api_progress_trends, "admin"),
]

COMPILED = [(method, re.compile(pattern), fn, access) for method, pattern, fn, access in ROUTES]


