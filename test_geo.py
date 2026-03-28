import time

# Import the required library
from geopy.geocoders import Nominatim

# Initialize Nominatim API
tic = time.perf_counter()
geolocator = Nominatim(user_agent="MyApp")
location = geolocator.geocode("Hyderabad")
toc = time.perf_counter()
print(f"time to run {toc - tic:0.4f}")
print("The latitude of the location is: ", location.latitude)
print("The longitude of the location is: ", location.longitude)

coordinates = "17.3850 , 78.4867"
tic = time.perf_counter()
location = geolocator.reverse(coordinates)
toc = time.perf_counter()
address = location.raw['address']
print(f"time to run {toc - tic:0.4f}")
print(f"Location {address}")
print(f"Country {address.get('country')}")

