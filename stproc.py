#
# Sports-Tracker Processor
#
# This script reads the sports-tracker sqlite database from the client app and exports a gpx file from the selected
# workout, in the same format as the sports-tracker website exports. This script as it is can be used to extract
# workouts which get stuck on the client and don't sync to the server. It can easily be extended to export all
# workouts, whether synced or not, to be imported elsewhere. The generated gpx doesn't exactly match the original data,
# because time information cannot be extracted from the polyline. Instead, the total workout time is divided by the
# number of track points and the delta time is added to each point.
#
# 2018 Steven Hampton
#
# Usage: python stproc.py key desc author > output.gpx
#
#            key       Google Maps API key
#            desc      description of workout to extract
#            author    name of author
#
# External requirements - polyline library: https://pypi.org/project/polyline/
#
import sqlite3
import polyline
import requests
import json
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import datetime
import sys

#
# a simple pretty-print function since ElementTree can't do it itself
#
def indent(elem, level=0):
  i = "\n" + level*"  "
  if len(elem):
    if not elem.text or not elem.text.strip():
      elem.text = i + "  "
    if not elem.tail or not elem.tail.strip():
      elem.tail = i
    for elem in elem:
      indent(elem, level+1)
    if not elem.tail or not elem.tail.strip():
      elem.tail = i
  else:
    if level and (not elem.tail or not elem.tail.strip()):
      elem.tail = i

#
# call GoogleMaps to get elevations for all given lat/lon pairs, and populate the XML with the data, plus the incremental time
#
def getelevations(requrl, trkseg, trktime, delta):
    requrl = requrl[:-1] # given url will have a | on the end
    # call the API and use SimpleNamespace to typecast the returned results
    retdata = json.loads(requests.get(requrl, verify=False).content, object_hook=lambda d: SimpleNamespace(**d))
    # loop through all lat/lon pairs returned, and get the elevation for each
    for result in retdata.results:
        trkpt = ET.SubElement(trkseg, 'trkpt') # add a new <trkpt> to the gpx document
        trkpt.set('lat', str(result.location.lat)) # set lat and lon from what Google Maps returns
        trkpt.set('lon', str(result.location.lng))
        ET.SubElement(trkpt, 'time').text = trktime.strftime("%Y-%m-%dT%H:%M:%SZ") # set time to sports-tracker format
        ET.SubElement(trkpt, 'ele').text = str(result.elevation) # get the elevation
        trktime += datetime.timedelta(milliseconds=delta) # increment the time by the total time divided by the number of points
        
    return trktime # return the incremented time, so it can be used back in the calling routine
  
# -------------------------------------------------------------------------------------------------------------
# start of main logic
# -------------------------------------------------------------------------------------------------------------

# parameters required - Google Maps API key, then workout description, then author name
key = sys.argv[1]
getdesc = sys.argv[2]
author = sys.argv[3]

# retrieve the necessary information from the sqlite database
conn = sqlite3.connect('stt.db') # place the sports-tracker database in the current directory
c = conn.cursor()
# select the necessary data from the given record
c.execute('SELECT polyline, startTime, totalTime FROM workoutheader WHERE description = "' + getdesc + '"')
# just fetch the first one - if multiple for given workout description, should change logic to select on id instead
vals = c.fetchone()
coords = polyline.decode(vals[0]) # convert polyline into array of lat/lon coordinates
trktime = datetime.datetime.fromtimestamp(vals[1]/1e3) # convert startTime to a python datetime
# calculate the millisecond delta by dividing the total workout time by the number of track points
delta = int(vals[2]*1e3/len(coords))

# set up for calls to Google Maps API
url = 'https://maps.googleapis.com/maps/api/elevation/json?key=' + key + '&locations='


# create an XML document in the sports-tracker format...
gpx = ET.Element('gpx')
metadata = ET.SubElement(gpx, 'metadata')
name = ET.SubElement(metadata, 'name')
desc = ET.SubElement(metadata, 'desc')
author = ET.SubElement(metadata, 'author')
aname = ET.SubElement(author, 'name')
link = ET.SubElement(metadata, 'link')
text = ET.SubElement(link, 'text')
trk = ET.SubElement(gpx, 'trk')
trkseg = ET.SubElement(trk, 'trkseg')
# ... and populate the header with the required information
gpx.set('xmlns', 'http://www.topografix.com/GPX/1/1')
gpx.set('xmlns:gpxtpx', 'http://www.garmin.com/xmlschemas/TrackPointExtension/v1')
gpx.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
gpx.set('creator', 'Sports Tracker')
gpx.set('version', '1.1')
gpx.set('xsi:schemaLocation', 'http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd http://www.garmin.com/xmlschemas/TrackPointExtension/v1 http://www.garmin.com/xmlschemas/TrackPointExtensionv1.xsd')
name.text = trktime.strftime("%d/%m/%Y %I:%M %p")
desc.text = getdesc
aname.text = author
link.set('href', 'www.sports-tracker.com')
text.text = "Sports Tracker"

# now iterate through all the lat/lon pairs from the polyline, add the elevations from Google Maps, and the delta times (giving
# a constant speed for the whole workout)
requrl = url
for coord in coords:
    # first build requests for Google Maps, with however many lat/lon pairs fit into 2000 chars
    requrl += str(coord[0]) + ',' + str(coord[1]) + '|'
    # once 2000 chars reached, make the call
    if len(requrl) > 2000:
        trktime = getelevations(requrl, trkseg, trktime, delta)
        requrl = url

# if, at the end there are some coords left over, make a final call        
if len(requrl) > len(url):
    trktime = getelevations(requrl, trkseg, trktime, delta)
    
# make the XML look nice    
indent(gpx)
# since output is to stdout, need to add this manually
print('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')
# now dump whole document to stdout
ET.dump(gpx)
