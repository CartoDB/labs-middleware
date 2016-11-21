# Basic auth middleware with CartoDB

This is a basic proof of concept of a middleware approach to the problem of how to authenticate and authorize users and allow them access to private datasets and visualization hosted on CartoDB.

In this example, we assume a private dataset called _items_ already exists on the user account on CartoDB. Items there can be filtered by a column called _category_.

We use [Flask](http://flask.pocoo.org/) and [Celery](http://www.celeryproject.org/) on a Python middleware for this example, but this architecture is totally platform-independent.

_DISCLAIMER:_ The code in this example has been written with the single purpose of being illustrative, and therefore does not at all meet the requirements of real-life, production code.

## Datasets

Private datasets on CartoDB require an API key in order to be accessed from external application with the SQL API (more [here](http://docs.cartodb.com/cartodb-platform/sql-api.html#authentication)). The API key cannot be used with `cartodb.js` and, in general, it's not a good idea to use it on client web applications. 

In our example, the middleware stores and uses the API key to talk to CartoDB, and exposes a single API endpoint to the client application:

* `GET /sql/items/`: Returns the list of items, as returned by CartoDB's SQL API. The middleware simply forwards the results of querying `select * from items` from the SQL API to the client application.

## Visualizations

On CartoDB, the way of visualizing private datasets is by using [named maps](http://docs.cartodb.com/cartodb-platform/maps-api.html#named-maps). For simplicity, we'll assume a suitable named map, called _testmap_ has already been [created](http://docs.cartodb.com/cartodb-platform/maps-api.html#create) on CartoDB for us, even though incorporating this step in our workflow would be pretty much straightforward.

In this case, because we don't want anyone, apart from authorized users, to see the maps, we'll be using [named maps protected by tokens](http://docs.cartodb.com/cartodb-platform/maps-api.html#named-maps-1).

We could follow the same approach as with the SQL API, and [make the middleware forward all the requests associated with displaying the map (instantiating the named map and retrieving the tiles)](https://gist.github.com/danicarrion/cf42e373efbae3224deff3d0265c49de), but this would have three important drawbacks:

* We'd miss all the power of CartoDB's caching engine.
* Our API towards the client app would be more complicated.
* We couldn't make use of cartodb.js on the client app.

Therefore, we've taken a different approach. The API from the middleware to the client exposes a single API endpoint:

* `GET /map/items/`: After receiving a request at this endpoint, the middleware generates a new random token and updates the named map on CartoDB (API-key authenticated `PUT` request to CartoDB's Maps API), adding the token to the list of authorized tokens for that map. It'll then return this to the client app: 
  * `username`: CartoDB's account user name, so that it doesn't need to be stored on the client app, which allows for more flexibility.
  * `name`: Name of the template map to be displayed, again for flexibility.
  * `token`: Token for the named map.

Now, with this token, the client app is now able to simply create the layers with cartodb.js, as usual.

This approach has its own disadvantage too: tokens for the named maps are made available to the client app. In order to mitigate the impact of this, the middleware in this example, after adding the token to the named map on CartoDB, simply creates a task to remove such token from the named map, that will be run 300s later. More sophisticated approaches can also be taken, like synchronizing that interval with the TTL of session cookies, and more.

## Authentication and authorization

In this example, authentication is handled by means of a simple login form, that checks username and password against the credentials of a single user defined in the configuration file.

* `GET /`: This renders the main page, that presents a login form if no session is active, or the work area if the user is already logged in.

If credentials match, a session is started, and every time a request arrives to any of the two endpoints exposed to the client app, the middleware verifies that a session is active before authorizing the request.

* `POST /`: Receives the username and password, checks such credentials, creates a user session and renders the main page with the work area.

A session can also be closed:

* `GET /logout/`: Closes current user session and redirects back to the mainpage.

This mechanism is totally lame and by no means should inspire any sort of real-life authentication/authorization workflow.

## Security of requests

Because we're using the API key, CartoDB enforces that all the requests coming and going from there use HTTPs. It is advisable, although not mandatory, to use HTTPs for the API between the middleware and the client app too.

## How to run the example

Just run `foreman start` and then point your browser to http://localhost:5000 (if using [foreman](https://github.com/ddollar/foreman)'s default settings).

## Demo

A working demo of this example, with a few minor changes, can be found at http://middleware.cartodb.io/

* User: middle
* Password: ware
