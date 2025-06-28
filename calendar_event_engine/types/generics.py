class GenericAddress:
    """
    Object used to store address information.
    Args:
        geom: Geo-coordinates for the point where the address is
        region: The state of this address
        locality: Town
        postalCode: ZipCode
        street: Street
        country: Country
    """
    geom: str
    locality: str
    postalCode: str
    street: str
    country: str
    region: str
    timezone: str
    description: str

    def __init__(self, geom: str = None, locality: str = None, postalCode: str = None, street:str=None, country: str="United States",
                 region: str = None, timezone:str = "America/New_York", description = ""):
        self.geom = geom
        self.locality = locality
        self.postalCode = postalCode
        self.street = street
        self.country = country
        self.region = region
        self.timezone = timezone
        self.description = description

    def __eq__(self, other):
        if type(other) != GenericAddress:
            return False
        other: GenericAddress
        local_postal_street: bool = other.locality == self.locality and other.postalCode == self.postalCode and other.street == self.street
        country_region_timezone: bool = other.country == self.country and other.region == self.region and other.timezone == self.timezone
        return local_postal_street and country_region_timezone and other.geom == self.geom and other.description == self.description

    def __str__(self):
        return f"{self.geom}, {self.locality}, {self.postalCode}, {self.street}, {self.region}"

class GenericEvent:
    """
    Object used to store event related information.
    Time is parsed with the local time zone available. Datetime + timezone
    """
    publisher_specific_info: dict

    title: str
    description: str
    begins_on: str
    ends_on: str
    picture: str
    online_address: str
    phone_address: str
    physical_address: GenericAddress

    def __init__(self, publisher_specific_info: dict, title: str, begins_on: str, description: str = None,
                 ends_on: str = None, online_address: str = None,
                 phone_address: str = None, physical_address: GenericAddress = None, picture: str = None):
        self.publisher_specific_info = publisher_specific_info
        self.title = title
        self.description = description
        self.begins_on = begins_on
        self.ends_on = ends_on
        self.online_address = online_address
        self.phone_address = phone_address
        self.physical_address = physical_address
        self.picture = picture

    @classmethod
    def default(cls):
        return cls(None, None, None)

    def __eq__(self, other):
        if type(other) != GenericEvent:
            return False
        else:
            other: GenericEvent
            time_and_address: bool = other.ends_on == self.ends_on and other.begins_on == self.begins_on and other.online_address == self.online_address and other.phone_address == self.phone_address and other.physical_address == self.physical_address
            description_and_title: bool = other.title == self.title and other.description == self.description
            return time_and_address and description_and_title and other.publisher_specific_info == self.publisher_specific_info

    def __str__(self):
        return f"Title: {self.title}, Begins On: {self.begins_on}, Ends On: {self.ends_on}\nDescription: {self.description}\nAddress: {self.physical_address}\nPicture URL: {self.picture}"


