from typing import Union


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

    geom: str | None
    locality: str | None
    postalCode: str | None
    street: str | None
    country: str
    region: str | None
    timezone: str
    description: str

    def __init__(
        self,
        geom: str | None = None,
        locality: str | None = None,
        postalCode: str | None = None,
        street: str | None = None,
        country: str = "United States",
        region: str | None = None,
        timezone: str = "America/New_York",
        description="",
    ):
        self.geom = geom
        self.locality = locality
        self.postalCode = postalCode
        self.street = street
        self.country = country
        self.region = region
        self.timezone = timezone
        self.description = description

    def _precise_equal(self, other: "GenericAddress") -> bool:
        local_postal_street: bool = (
            other.locality == self.locality
            and other.postalCode == self.postalCode
            and other.street == self.street
        )
        country_region_timezone: bool = (
            other.country == self.country
            and other.region == self.region
            and other.timezone == self.timezone
        )
        return country_region_timezone and local_postal_street

    def fuzzy_equal(self, other: Union["GenericAddress", None]):
        if not isinstance(other, GenericAddress):
            return False
        precise = self._precise_equal(other)
        return precise and other.description == self.description

    def __eq__(self, other):
        if not isinstance(other, GenericAddress):
            return False
        precise = self._precise_equal(other)
        return (
            other.geom == self.geom
            and precise
            and other.description == self.description
        )

    def __str__(self):
        return f"{self.geom}, {self.locality}, {self.postalCode}, {self.street}, {self.region}"


class GenericEvent:
    """
    Object used to store event related information.
    Time is parsed with the local time zone available. Datetime + timezone
    """

    publisher_specific_info: dict

    title: str
    description: str | None
    begins_on: str
    ends_on: str | None
    picture: str | None
    online_address: str | None
    phone_address: str | None
    physical_address: GenericAddress | None

    def __init__(
        self,
        publisher_specific_info: dict,
        title: str,
        begins_on: str,
        description: str | None = None,
        ends_on: str | None = None,
        online_address: str | None = None,
        phone_address: str | None = None,
        physical_address: GenericAddress | None = None,
        picture: str | None = None,
    ):
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

    def fuzzy_equal(self, other: "GenericEvent") -> bool:
        time_test = other.ends_on == self.ends_on and other.begins_on == self.begins_on
        physical_address_test: bool = (
            self.physical_address == other.physical_address
            if self.physical_address is None
            else self.physical_address.fuzzy_equal(other.physical_address)
        )
        address_test: bool = (
            other.online_address == self.online_address
            and other.phone_address == self.phone_address
            and physical_address_test
        )
        title: bool = other.title.strip() == self.title.strip()
        publisher_info: bool = (
            other.publisher_specific_info == self.publisher_specific_info
        )
        return time_test and address_test and title and publisher_info

    def __eq__(self, other):
        if not isinstance(other, GenericEvent):
            return False
        else:
            return self.fuzzy_equal(other) and self.description == other.description

    def __str__(self):
        return f"Title: {self.title}, Begins On: {self.begins_on}, Ends On: {self.ends_on}\nDescription: {self.description}\nAddress: {self.physical_address}\nPicture URL: {self.picture}"
