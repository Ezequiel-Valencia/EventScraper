"""GraphQL documents for the Mobilizon API.

All user supplied values are passed as GraphQL variables, never interpolated
into the document, so quotes/backslashes in titles, descriptions or passwords
cannot break (or inject into) a request.
Schema: https://github.com/framasoft/mobilizon/tree/main/lib/graphql/schema
"""

from gql import gql
from graphql import DocumentNode

# Argument types of the createEvent mutation, keyed by MobilizonEvent field.
_CREATE_EVENT_ARG_TYPES = {
    "organizerActorId": "ID!",
    "attributedToId": "ID",
    "title": "String!",
    "description": "String!",
    "beginsOn": "DateTime!",
    "endsOn": "DateTime",
    "status": "EventStatus",
    "visibility": "EventVisibility",
    "joinOptions": "EventJoinOptions",
    "tags": "[String]",
    "picture": "MediaInput",
    "onlineAddress": "String",
    "category": "EventCategory",
    "physicalAddress": "AddressInput",
}


def create_event(variables: dict) -> DocumentNode:
    """Only declares the variables actually provided, so omitted arguments
    fall back to Mobilizon's defaults instead of being sent as null."""
    declarations = ", ".join(f"${k}: {_CREATE_EVENT_ARG_TYPES[k]}" for k in variables)
    arguments = ", ".join(f"{k}: ${k}" for k in variables)
    return gql(
        f"mutation CreateEvent({declarations}) {{ createEvent({arguments}) {{ id uuid }} }}"
    )


DELETE_EVENT = gql(
    "mutation DeleteEvent($eventId: ID!) { deleteEvent(eventId: $eventId) { id } }"
)

# Sent as a raw multipart request: Absinthe expects the "file" variable to name
# a multipart part, which differs from the spec gql's upload support implements.
UPLOAD_MEDIA = """
mutation UploadMedia($file: Upload!, $name: String!, $actorId: ID) {
  uploadMedia(file: $file, name: $name, actorId: $actorId) { uuid }
}
"""

REMOVE_MEDIA = gql(
    "mutation RemoveMedia($uuid: UUID!) { removeMedia(uuid: $uuid) { uuid } }"
)

LOGIN = gql(
    """
mutation Login($email: String!, $password: String!) {
  login(email: $email, password: $password) { accessToken refreshToken }
}
"""
)

LOGOUT = gql(
    "mutation Logout($refreshToken: String!) { logout(refreshToken: $refreshToken) }"
)

IDENTITIES = gql(
    "query Identities { identities { id type preferredUsername name url } }"
)

GROUPS = gql(
    """
query Groups($name: String, $page: Int, $limit: Int) {
  loggedUser {
    id
    memberships(name: $name, page: $page, limit: $limit) {
      total
      elements {
        role
        actor { id type preferredUsername name }
        parent { id type preferredUsername name }
      }
    }
  }
}
"""
)
