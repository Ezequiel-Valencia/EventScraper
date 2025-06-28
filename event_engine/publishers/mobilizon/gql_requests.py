from enum import Enum

from gql import gql
from pydantic import BaseModel

from event_engine.publishers.mobilizon.types import MobilizonEvent


# TODO: Clean all text for dangerous input

# EventType = MobilizonTypes.EventType
# https://github.com/framasoft/mobilizon/blob/main/docs/dev.md

# Cleaning Received Text
# https://stackoverflow.com/questions/10993612/how-to-remove-xa0-from-string-in-python

def _conditional_attribute(key: str, value):
  return ((key + ": " + str(value) + ",\n") if value is not None else "")


def conditional_gql_inputs(classDataObject: BaseModel or dict):
  classDict: dict = classDataObject.dict() if isinstance(classDataObject, (BaseModel)) else classDataObject
  gqlString = """"""
  for key, value in classDict.items():
    valueType = type(value)
    if (valueType is str or valueType is int):
      if (valueType is str):
        value = value.replace('"', "'")
        # value = re.sub(r"(\n{2,})|( +(?=\n))", "", value) #No multiple newlines in succession
        value = f'"""{value}"""'
      gqlString += _conditional_attribute(key, value)
    elif (isinstance(value, Enum)):
      value = value.value
      gqlString += _conditional_attribute(key, value)
    elif (valueType is dict and value is not None):
      gqlString = f"""{gqlString}{key}:{{
          {conditional_gql_inputs(value)}
        }},"""
  return gqlString

# conditional_gql_inputs(EventType(title="f", description="f", actorID=1, picture=EventParameters.MediaInput(name="fd", url="bar")))


# ==== GQL : Events ====
class EventGQL:
    def createEventGQL(eventInformation: MobilizonEvent):
        gqlString = f"""
        mutation {{ createEvent(
          {conditional_gql_inputs(eventInformation)}
          )
          {{
            id
            uuid
          }}
        }}
    """
        return gql(gqlString)
    
    def uploadMediaRawGQL():
      gqlString = """
        mutation($file: Upload!, $name: String!, $actorId: ID){
          uploadMedia(
            file: $file,
            name: $name,
            actorId: $actorId
          ){
            id
          }
        }
      """
      return gqlString

#           {("picture: " + eventInformation.picture) + "," if eventInformation.picture != None else ""} 

# ==== GQL : credentials ====


class AuthenticationGQL:
    def loginGQL(email, password):
        gqlString = f"""
      mutation {{
      login(
      email: {email}, 
      password: {password}) {{
        accessToken   
        refreshToken
      }}
    }}
    """
        return gql(gqlString)

    def logoutGQL(refreshToken):
        gqlString = f"""
      mutation {{
      logout(refreshToken: {refreshToken})
    }}
    """
        return gql(gqlString)

    def refreshTokenGQL(refreshToken):
        gqlString = f"""
      mutation {{ RefreshToken(
      refreshToken: {refreshToken}) {{
	    accessToken   
      refreshToken
      }}
    }}"""
        return gql(gqlString)
    

class ActorsGQL:
  def getIdentities():
    gqlString = """
    query {
        identities{
          id
          type
          preferredUsername
          name
          url
        }
      }
    """
    return gql(gqlString)
  
  def getGroups(membershipName, page=1, limit=30):
    gqlString = f"""
    query {{
      loggedUser{{
        id
        memberships(name: {membershipName}, page: {page}, limit: {limit}){{
          total
          elements{{
            role
            actor{{
              id
              type
              preferredUsername
              name
            }}
            parent{{
              id
              type
              preferredUsername
              name
            }}
          }}
        }}
      }}
    }}
    """
    return gql(gqlString)


# UPDATE_GQL = gql("""
# mutation updateEvent($id: ID!, $title: String, $description: String, $beginsOn: DateTime, $endsOn: DateTime, $status: EventStatus, $visibility: EventVisibility, $joinOptions: EventJoinOptions, $draft: Boolean, $tags: [String], $picture: PictureInput, $onlineAddress: String, $phoneAddress: String, $organizerActorId: ID, $attributedToId: ID, $category: String, $physicalAddress: AddressInput, $options: EventOptionsInput, $contacts: [Contact]) {
#   updateEvent(eventId: $id, title: $title, description: $description, beginsOn: $beginsOn, endsOn: $endsOn, status: $status, visibility: $visibility, joinOptions: $joinOptions, draft: $draft, tags: $tags, picture: $picture, onlineAddress: $onlineAddress, phoneAddress: $phoneAddress, organizerActorId: $organizerActorId, attributedToId: $attributedToId, category: $category, physicalAddress: $physicalAddress, options: $options, contacts: $contacts) {
# 	id
# 	uuid
#   }
# }
# """)


# CANCEL_GQL = gql("""
# mutation updateEvent($eventId: ID!) {
#   updateEvent(eventId: $eventId, status: CANCELLED) {
# 	id
# 	uuid
#   }
# }
# """)

# CONFIRM_GQL = gql("""
# mutation updateEvent($eventId: ID!) {
#   updateEvent(eventId: $eventId, status: CONFIRMED) {
# 	id
# 	uuid
#   }
# }
# """)


# DELETE_GQL = gql("""
# mutation DeleteEvent($eventId: ID!) {
#   deleteEvent(eventId: $eventId) {
# 	id
#   }
# }
# """)

# # ==== /GQL : Events ====

# # ==== GQL : Actors ====

# CREATE_USER_GQL = gql("""
# mutation createUser($email: String!, $locale: String="fr", $password: String!) {
#   createUser(email: $email, locale: $locale, password: $password) {
# 	id
#   }
# }""")

# CREATE_GROUP_GQL = gql("""
# mutation createGroup($name: String, $preferredUsername: String!, $summary: String = "") {
#   createGroup(name: $name, preferredUsername: $preferredUsername, summary: $summary) {
# 	id
#   }
# }""")

# CREATE_PERSON_GQL = gql("""
# mutation createPerson($name: String, $preferredUsername: String!, $summary: String = "") {
#   createPerson(name: $name, preferredUsername: $preferredUsername, summary: $summary) {
# 	id   url
#   }
# }""")

# CREATE_MEMBER_GQL = gql("""
# mutation inviteMember($groupId: ID!, $targetActorUsername: String!) {
#   inviteMember(groupId: $groupId, targetActorUsername: $targetActorUsername) {
# 	id   role
#   }
# }""")

# UPDATE_MEMBER_GQL = gql("""
# mutation updateMemberRole($memberId: ID!, $role:MemberRoleEnum!) {
#   updateMember(memberId: $memberId, role: $role) {
# 	id   role
#   }
# }""")

# # ==== /GQL : Users ====

# # ==== /GQL : credentials ====

# # ==== GQL : identities - actors - persons and groups ====

# PROFILES_GQL = gql("""
# query Identities { identities { ...ActorFragment } }
# fragment ActorFragment on Actor { id type preferredUsername name url}
# """)

# GROUPS_GQL = gql("""
# query LoggedUserMemberships($membershipName: String, $page: Int, $limit: Int) {
#   loggedUser {
# 	memberships(name: $membershipName, page: $page, limit: $limit) {
# 	  elements {
# 		role
# 		actor { ...ActorFragment }
# 		parent { ...ActorFragment }
# 	  }
# 	}
#   }
# }
# fragment ActorFragment on Actor {  id type  preferredUsername  name }
# """)


"""
        mutation {{ createEvent(
          organizerActorId: {eventInformation.organizerActorId},
          attributedToId: {eventInformation.attributedToId}, 
          title: {eventInformation.title}, 
          description: {eventInformation.description}, 
          beginsOn: "2020-10-29T00:00:00+01:00"
          endsOn: "2022-03-31T23:59:59+02:00"
          status: {eventInformation.status}, 
          visibility: {eventInformation.visibility}, 
          joinOptions: {eventInformation.joinOptions}, 
          draft: {eventInformation.draft}, 
          {_conditional_attribute("picture", eventInformation.picture)}
          {_conditional_attribute("onlineAddress", eventInformation.onlineAddress)}
          {_conditional_attribute("phoneAddress", eventInformation.phoneAddress)}
          {_conditional_attribute("category", eventInformation.category)}
          physicalAddress: {{
              geom: {eventInformation.physicalAddress.geom},
              locality: {eventInformation.physicalAddress.locality},
              postalCode: {eventInformation.physicalAddress.postalCode},
              street: {eventInformation.physicalAddress.street},
              country: {eventInformation.physicalAddress.country}
            }},
          {_conditional_attribute("contacts", eventInformation.contacts)}
          )
          {{
            id
            uuid
          }}
        }}
    """
