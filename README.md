# XPublish OGC Core

Enable Xpublish plugins that support various OGC methods to serve via fully OGC compliant routes.

_Currently it's a very alpha way to demo how we could do this. You have been warned._

This works by creating an `app_router` that responds to more general OGC endpoints like `/collections`, `/collections/{collection_id}` with eventually compliant responses.

It also registers new `hookspec`s that other plugins can implement.

- `ogc_router` which allows adding to any OGC route (probably should add an `ogc_collections_router` to be more specific).
- `ogc_collection_dataqueries` that allows each plugin to advertise their routes in a `/collections/{collection_id}` response.
