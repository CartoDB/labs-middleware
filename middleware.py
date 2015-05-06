#!/usr/bin/env python
import ConfigParser
import json
import random
import string
import os
import requests
import ssl
from celery import Celery
from flask import Flask, request, session, redirect, url_for, render_template, flash, Response, jsonify, send_from_directory


class Config(object):
    def __init__(self, config_file_name):
        self.config_parser = ConfigParser.RawConfigParser()
        self.config_parser.read(config_file_name)

    def get(self, section, key):
        try:
            return self.config_parser.get(section, key)
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            return os.environ.get("%s_%s" % (section.upper(), key.upper()), None)

config = Config("middleware.conf")


def make_celery(app):
    celery = Celery(app.import_name, broker=app.config['CELERY_BROKER_URL'])
    celery.conf.update(app.config)
    TaskBase = celery.Task
    class ContextTask(TaskBase):
        abstract = True
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)
    celery.Task = ContextTask
    return celery


app = Flask(__name__)

if config.get('platform', 'debug'):
    app.debug = True

app.secret_key = config.get('platform', 'secret_key')
app.config.update(
    CELERY_BROKER_URL=config.get('platform', 'redis_url'),
    CELERY_RESULT_BACKEND=config.get('platform', 'redis_url')
)

celery = make_celery(app)

@app.route('/js/<path:path>')
def send_js(path):
    return send_from_directory('static/js', path)


@app.route('/css/<path:path>')
def send_css(path):
    return send_from_directory('static/css', path)


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == config.get('auth', 'username') and password == config.get('auth', 'password'):
            session['username'] = request.form['username']
        else:
            flash('Invalid credentials')

    return render_template('index.html', user=session['username'] if "username" in session else None)

@app.route('/logout/')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))


@app.route(config.get('platform', 'sql_endpoint'))
def sql_provinces():
    if "username" not in session:
        return redirect(url_for('index'))

    # Call CartoDB's SQL API
    params = {
        "q": config.get('sql', 'query'),
        "api_key": config.get('cartodb', 'api_key'),
    }
    r = requests.get(config.get('cartodb', 'sql_endpoint'), params)

    return Response(r.content, mimetype='application/json')


named_map = {
    "version": "0.0.1",
    "name": config.get('map', 'name'),
    "auth": {
        "method": "token",
        "valid_tokens": []
    },
    "placeholders": {
        "color": {
            "type": "css_color",
            "default": "red"
        },
        "filter": {
            "type": "number",
            "default": 1
        }
    },
    "layergroup": {
        "version": "1.0.1",
        "layers": [
            {
                "type": "cartodb",
                "options": {
                    "cartocss_version": "2.1.1",
                    "cartocss": "#layer { polygon-fill: <%= color %>; }",
                    "sql": config.get('map', 'sql')
                }
            }
        ]
    }
}

@celery.task()
def delete_token(token):
    try:
        named_map["auth"]["valid_tokens"].remove(token)
    except ValueError:
        pass

    requests.put(os.path.join(config.get('cartodb', 'maps_endpoint'), "named", config.get('map', 'name')),
                 data=json.dumps(named_map),
                 params={"api_key": config.get('cartodb', 'api_key')},
                 headers={'content-type': 'application/json'})


@app.route(config.get('platform', 'map_endpoint'))
def map_provinces():
    map_name = config.get('map', 'name')

    new_token = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(20))
    named_map["auth"]["valid_tokens"].append(new_token)

    requests.put(os.path.join(config.get('cartodb', 'maps_endpoint'), "named", map_name),
                 data=json.dumps(named_map),
                 params={"api_key": config.get('cartodb', 'api_key')},
                 headers={'content-type': 'application/json'})

    delete_token.apply_async((new_token,), countdown=config.get('maps', 'delete_token_delay'))

    return jsonify({"token": new_token,
                    "username": config.get('cartodb', 'username'),
                    "name": map_name})


if __name__ == "__main__":
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    context.load_cert_chain(config.get('platform', 'server_cert'), config.get('platform', 'server_key'))

    app.run(host=config.get('platform', 'host'), port=int(config.get('platform', 'port')), ssl_context=context)
