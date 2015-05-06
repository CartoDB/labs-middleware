#!/usr/bin/env python
import ConfigParser
import os
import requests
import ssl
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


app = Flask(__name__)

if config.get('platform', 'debug'):
    app.debug = True

app.secret_key = config.get('platform', 'secret_key')


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


@app.route(config.get('platform', 'map_endpoint'))
def map_provinces():
    return jsonify({"token": config.get('map', 'token'),
                    "username": config.get('cartodb', 'username'),
                    "name": config.get('map', 'name')})


if __name__ == "__main__":
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    context.load_cert_chain(config.get('platform', 'server_cert'), config.get('platform', 'server_key'))

    app.run(host=config.get('platform', 'host'), port=int(config.get('platform', 'port')), ssl_context=context)
