from dataclasses import dataclass
from typing import Union


# eq=False: equality is defined by hand below, because `fuzzy_equal` and `__eq__`
# deliberately ignore some fields.
@dataclass(eq=False)
class GenericAddress:
    """
    Object used to store address information.
    Args:
        latitude: Latitude of the address in decimal degrees (WGS 84)
        longitude: Longitude of the address in decimal degrees (WGS 84)
        locality: Town
        postalCode: ZipCode
        street: Street
        country: Country
        region: The state of this address
        timezone: IANA timezone name
        description: Free text description of the place
    """

    latitude: float | None = None
    longitude: float | None = None
    locality: str | None = None
    postalCode: str | None = None
    street: str | None = None
    country: str = "United States"
    region: str | None = None
    timezone: str = "America/New_York"
    description: str = ""

    def _precise_equal(self, other: "GenericAddress") -> bool:
        return (
            other.locality == self.locality
            and other.postalCode == self.postalCode
            and other.street == self.street
            and other.country == self.country
            and other.region == self.region
            and other.timezone == self.timezone
        )

    def fuzzy_equal(self, other: Union["GenericAddress", None]) -> bool:
        """Equal apart from the coordinates."""
        if not isinstance(other, GenericAddress):
            return False
        return self._precise_equal(other) and other.description == self.description

    def __eq__(self, other):
        if not isinstance(other, GenericAddress):
            return False
        return (
            self.fuzzy_equal(other)
            and other.latitude == self.latitude
            and other.longitude == self.longitude
        )

    __hash__ = None  # type: ignore[assignment]  # mutable, so unhashable

    def __str__(self):
        return f"({self.latitude}, {self.longitude}), {self.locality}, {self.postalCode}, {self.street}, {self.region}"


@dataclass(eq=False)
class GenericEvent:
    """
    Object used to store event related information.
    Times are ISO 8601 strings that include a UTC offset.
    """

    publisher_specific_info: dict
    title: str
    begins_on: str
    description: str | None = None
    ends_on: str | None = None
    online_address: str | None = None
    phone_address: str | None = None
    physical_address: GenericAddress | None = None
    picture: str | None = None

    def fuzzy_equal(self, other: "GenericEvent") -> bool:
        """Equal apart from the description and the address' coordinates."""
        physical_address_test: bool = (
            other.physical_address is None
            if self.physical_address is None
            else self.physical_address.fuzzy_equal(other.physical_address)
        )
        return (
            other.ends_on == self.ends_on
            and other.begins_on == self.begins_on
            and other.online_address == self.online_address
            and other.phone_address == self.phone_address
            and physical_address_test
            and other.title.strip() == self.title.strip()
            and other.publisher_specific_info == self.publisher_specific_info
        )

    def __eq__(self, other):
        if not isinstance(other, GenericEvent):
            return False
        return self.fuzzy_equal(other) and self.description == other.description

    __hash__ = None  # type: ignore[assignment]  # mutable, so unhashable

    def __str__(self):
        return f"Title: {self.title}, Begins On: {self.begins_on}, Ends On: {self.ends_on}\nDescription: {self.description}\nAddress: {self.physical_address}\nPicture URL: {self.picture}"
