FROM python:3.12-alpine

WORKDIR /srv

COPY app.py api.py api_common.py api_auth.py api_questions.py api_practice.py api_issues.py api_admin.py webserver.py db.py auth.py quiz.py import_questions.py ./
COPY static ./static

RUN adduser -D -H -u 1000 appuser \
    && mkdir -p /srv/data \
    && chown -R appuser:appuser /srv
USER appuser

ENV PORT=8001 \
    QUIZ_HOST=0.0.0.0 \
    QUIZ_DB=/srv/data/questions.db

VOLUME ["/srv/data"]

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8001')+'/healthz').read()" || exit 1

CMD ["python", "app.py"]
