from enum import Enum

from pydantic import BaseModel


class EventParameters:
    class Status(Enum):
        confirmed = "CONFIRMED"
        canceled = "CANCELED"
        tentative = "TENTATIVE"

    class Visibility(Enum):
        public = "PUBLIC"

    class JoinOptions(Enum):
        free = "FREE"
        invite = "INVITE"
        restricted = "RESTRICTED"

    class Categories(Enum):
        arts = "ARTS"
        book_clubs = "BOOK_CLUBS"
        business = "BUSINESS"
        causes = "CAUSES"
        comedy = "COMEDY"
        crafts = "CRAFTS"
        food_drink = "FOOD_DRINK"
        health = "HEALTH"
        music = "MUSIC"
        community = "COMMUNITY"
        family_education = "FAMILY_EDUCATION"
        fashion_beauty = "FASHION_BEAUTY"
        film_media = "FILM_MEDIA"
        games = "GAMES"
        language_culture = "LANGUAGE_CULTURE"
        learning = "LEARNING"
        lgbtq = "LGBTQ"
        movements_politics = "MOVEMENTS_POLITICS"
        networking = "NETWORKING"
        party = "PARTY"
        performing_visual_arts = "PERFORMING_VISUAL_ARTS"
        pets = "PETS"
        photography = "PHOTOGRAPHY"
        outdoors_adventure = "OUTDOORS_ADVENTURE"
        spirituality_religion_beliefs = "SPIRITUALITY_RELIGION_BELIEFS"
        science_tech = "SCIENCE_TECH"
        sports = "SPORTS"
        theatre = "THEATRE"
        default = "MEETING"

    class Address(BaseModel):
        """Address object matching Mobilizon's AddressInput.

        Args:
            geom: Geo-coordinates for the point where the address is ("lon;lat")
            region: The state of this address
            locality: Town
            postalCode: ZipCode
            street: Street
            country: Country
            originId: The ID affiliated with the api that gave the location info
        """

        locality: str
        postalCode: str = ""
        street: str = ""
        country: str = "United States"
        region: str = "Connecticut"
        geom: str | None = None
        timezone: str = "America/New_York"
        description: str = ""
        originId: str | None = None

    class MediaInput(BaseModel):
        # https://github.com/framasoft/mobilizon/blob/main/lib/graphql/schema/media.ex
        mediaUuid: str


class MobilizonEvent(BaseModel):
    """Arguments of Mobilizon's createEvent mutation.

    Args:
        organizerActorId: Actor ID
        attributedToId: Group ID
        beginsOn/endsOn: ISO 8601 datetimes, e.g. 2025-05-25T00:00:00-04:00
    """

    organizerActorId: int = 0
    attributedToId: int
    title: str
    description: str = ""  # Mobilizon requires a non-null description
    beginsOn: str
    endsOn: str | None = None
    status: EventParameters.Status = EventParameters.Status.confirmed
    visibility: EventParameters.Visibility = EventParameters.Visibility.public
    joinOptions: EventParameters.JoinOptions = EventParameters.JoinOptions.free
    tags: list[str] | None = None
    picture: EventParameters.MediaInput | None = None
    onlineAddress: str | None = None
    category: EventParameters.Categories | None = None
    physicalAddress: EventParameters.Address | None = None

    def to_gql_variables(self) -> dict:
        return self.model_dump(mode="json", exclude_none=True)


class Actor(BaseModel):
    id: int
    name: str
    preferredUsername: str
    type: str
    url: str
