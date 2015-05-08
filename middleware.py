#!/usr/bin/env python
import ConfigParser
import json
import random
import string
import os
import requests
from celery import Celery
from flask import Flask, request, session, redirect, url_for, render_template, flash, Response, jsonify


class Config(object):
    """
    Looks for config options in a config file or as an environment variable
    """
    def __init__(self, config_file_name):
        self.config_parser = ConfigParser.RawConfigParser()
        self.config_parser.read(config_file_name)

    def get(self, section, option):
        """
        Tries to find an option in a section inside the config file. If it's not found or if there is no
        config file at all, it'll try to get the value from an enviroment variable built from the section
        and options name, by joining the uppercase versions of the names with an underscore. So, if the section is
        "platform" and the option is "secret_key", the environment variable to look up will be PLATFORM_SECRET_KEY
        :param section: Section name
        :param option: Optionname
        :return: Configuration value
        """
        try:
            return self.config_parser.get(section, option)
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            return os.environ.get("%s_%s" % (section.upper(), option.upper()), None)

config = Config("middleware.conf")


def make_celery(app):
    """
    Build Celery's entry point
    :param app: Flask application object
    :return: Celery instance
    """
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
def sql_items():
    if "username" not in session:
        return redirect(url_for('index'))

    # Call CartoDB's SQL API
    params = {
        "q": config.get('sql', 'query'),
        "api_key": config.get('cartodb', 'api_key'),
    }
    r = requests.get(config.get('cartodb', 'sql_endpoint'), params)

    return Response(r.content, mimetype='application/json')


# CartoDB's API doesn't support PATCH at the moment of writing this, so we're using this object
# to help us build PUT requests
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

    # Call CartoDB's Maps API to remove the token from the named map
    # This will also invalidate the cache for the tiles on the CDN with this token
    requests.put(os.path.join(config.get('cartodb', 'maps_endpoint'), "named", config.get('map', 'name')),
                 data=json.dumps(named_map),
                 params={"api_key": config.get('cartodb', 'api_key')},
                 headers={'content-type': 'application/json'})


@app.route(config.get('platform', 'map_endpoint'))
def map_items():
    map_name = config.get('map', 'name')

    new_token = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(20))
    named_map["auth"]["valid_tokens"].append(new_token)

    # Call CartoDB's Maps API to add the token to the named map
    requests.put(os.path.join(config.get('cartodb', 'maps_endpoint'), "named", map_name),
                 data=json.dumps(named_map),
                 params={"api_key": config.get('cartodb', 'api_key')},
                 headers={'content-type': 'application/json'})

    # Create Celery task to delete the token after a certain interval
    delete_token.apply_async((new_token,), countdown=config.get('maps', 'delete_token_delay'))

    return jsonify({"token": new_token,
                    "username": config.get('cartodb', 'username'),
                    "name": map_name})
