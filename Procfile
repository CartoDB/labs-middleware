web: gunicorn middleware:app --log-file=-
worker: celery worker --app=middleware.celery
