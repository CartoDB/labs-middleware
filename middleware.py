#!/usr/bin/env python
import ConfigParser
import requests
import ssl
from flask import Flask, request, session, redirect, url_for, render_template, flash, Response, jsonify


app = Flask(__name__)

config = ConfigParser.RawConfigParser()
config.read("middleware.conf")

app.secret_key = config.get('platform', 'secret_key')

if config.get('platform', 'debug'):
    app.debug = True


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

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))


@app.route("/sql/provinces/")
def sql_provinces():
    if "username" not in session:
        return redirect(url_for('index'))

    # Call CartoDB's SQL API
    params = {
        "q": "select cartodb_id, ccaa, codigo, nombre from provincias",
        "api_key": config.get('cartodb', 'api_key'),
    }
    r = requests.get(config.get('cartodb', 'sql_endpoint'), params)

    return Response(r.content, mimetype='application/json')


@app.route("/map/provinces/")
def map_provinces():
    return jsonify({"token": config.get('map', 'token'),
                    "username": config.get('cartodb', 'username'),
                    "name": config.get('map', 'name')})


if __name__ == "__main__":
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    context.load_cert_chain(config.get('platform', 'server_cert'), config.get('platform', 'server_key'))

    app.run(host=config.get('platform', 'host'), port=int(config.get('platform', 'port')), ssl_context=context)
