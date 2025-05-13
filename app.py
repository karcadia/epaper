#!/usr/bin/python
# -*- coding:utf-8 -*-
import sys
import os
import logging
import time
import json
from pprint import pprint
from datetime import datetime, timedelta
from xml.etree import ElementTree
from xml.dom import minidom
# end stdlib
import requests
import pytz
from PIL import Image,ImageDraw,ImageFont
import epd5in65f
# exceptions
from requests.exceptions import ConnectionError

APP_NAME = 'epaper'
DEBUG = False
MAX_WIDTH = 22
poll_world_weather = True

format = "%(asctime)s [" + APP_NAME + "] %(levelname)s %(message)s"
datefmt = "[%Y-%m-%dT%H:%M:%S]"
log = logging.getLogger(APP_NAME)
formatter = logging.Formatter(format, datefmt=datefmt)
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(formatter)
log.addHandler(consoleHandler)
log.setLevel(logging.INFO)
log.propagate = False
if DEBUG:
    log.setLevel(logging.DEBUG)

def convert_to_central_time(utc_string):
    utc_time = datetime.fromisoformat(utc_string)
    chicago = pytz.timezone('America/Chicago')
    chicago_time = utc_time.replace(tzinfo=pytz.utc).astimezone(chicago)
    return chicago_time

def calc_wind_arrow(bearing):
    if bearing > 330:
        dir = 'North'
    elif bearing > 300:
        dir = 'Northwest'
    elif bearing > 240:
        dir = 'West'
    elif bearing > 200:
        dir = 'Southwest'
    elif bearing > 150:
        dir = 'South'
    elif bearing > 120:
        dir = 'Southeast'
    elif bearing > 70:
        dir = 'East'
    elif bearing > 20:
        dir = 'Northeast'
    else:
        dir = 'North'

    if dir == 'West':
        return '\u2190'
    elif dir == 'North':
        return '\u2191'
    elif dir == 'East':
        return '\u2192'
    elif dir == 'South':
        return '\u2193'
    elif dir == 'Northwest':
        return '\u2196'
    elif dir == 'Northeast':
        return '\u2197'
    elif dir == 'Southeast':
        return '\u2198'
    elif dir == 'Southwest':
        return '\u2199'

def main():
    HA_TOKEN = os.getenv('HA_TOKEN')
    if not HA_TOKEN:
        print('App cannot start without an HA_TOKEN.')
        exit(1)
    PLEX_TOKEN = os.getenv('PLEX_TOKEN')
    if not PLEX_TOKEN:
        print('App cannot start without a PLEX_TOKEN.')
        exit(1)
    WEATHER_TOKEN = os.getenv('WEATHER_TOKEN')
    if not WEATHER_TOKEN:
        print('App cannot start without a WEATHER_TOKEN.')
        exit(1)
    ROUTER_KEY = os.getenv('ROUTER_KEY')
    if not ROUTER_KEY:
        print('App cannot start without a ROUTER_KEY.')
        exit(1)
    ROUTER_SECRET = os.getenv('ROUTER_SECRET')
    if not ROUTER_SECRET:
        print('App cannot start without a ROUTER_SECRET.')
        exit(1)

    epc = EPC()

    try:
#        while True:
            log.info('Application started. Refreshing sensor data.')
            #epc.refresh_worldweather(WEATHER_TOKEN)
            epc.refresh_router_updates(ROUTER_KEY, ROUTER_SECRET)
            epc.refresh_plex(PLEX_TOKEN, HA_TOKEN)
            epc.refresh_sensors(HA_TOKEN)

            log.info('Sensor data fetched. Initializing screen.')
            epc.init_screen()

            log.info('Screen initialized. Starting screen draw.')
            epc.draw()
            log.info('Screen draw complete. Goodbye.')
#            log.info('Screen draw complete, sleeping until next cycle.')
#            time.sleep(900)

    except IOError as e:
        log.info(e)

    except KeyboardInterrupt:
        log.info("ctrl-c detected, cleaning up...")
        epd5in65f.epdconfig.module_exit(cleanup=True)
        exit()

class EPC:
    def __init__(self):
        self.epd = epd5in65f.EPD()
        self.PLEX_API = 'http://mccormicom.com:32400/'
        self.holiday = None

    def init_screen(self):
        self.epd.init()

    def clear(self):
        self.epd.Clear()

    def shutdown(self):
        epd5in65f.epdconfig.module_exit(cleanup=True)

    def say_plex_is_down(self, HA_TOKEN):
        now = datetime.now()
        if now.hour < 8:
            log.info('Skipping auditory warning since we are in quiet hours.')
        headers = {
            "Authorization": f"Bearer {HA_TOKEN}",
            "content-type": "application/json"
        }
        url = 'https://mccormicom.com:8123/api/webhook/plex-is-down-hJ4w0G1gjCMM-XwdCSGYv8d1'
        req = requests.request('GET', url=url)

    def refresh_sensors(self, HA_TOKEN):
        headers = {
            "Authorization": f"Bearer {HA_TOKEN}",
            "content-type": "application/json"
        }

        url = 'https://mccormicom.com:8123/api/states'
        req = requests.request('GET', url=url, headers=headers)

        state_list = json.loads(req.text)
        for item in state_list:
            if item['entity_id'] == 'sun.sun':
                self.sun_status = item['state']
            if item['entity_id'] == 'sensor.sun_next_rising':
                chicago_time = convert_to_central_time(item['state'])
                next_dawn = chicago_time.isoformat().split('T')[1].split('-')[0]
                self.next_dawn = next_dawn
            if item['entity_id'] == 'sensor.sun_next_setting':
                chicago_time = convert_to_central_time(item['state'])
                next_dusk = chicago_time.isoformat().split('T')[1].split('-')[0]
                self.next_dusk = next_dusk
            if item['entity_id'] == 'weather.forecast_home':
                self.weather = item['state']
                temperat = str(item['attributes']['temperature']) + item['attributes']['temperature_unit']
                self.weather_temperature = temperat
                self.weather_humidity = str(item['attributes']['humidity']) + '%'
                self.weather_uv_index = item['attributes']['uv_index']
                pressure = str(item['attributes']['pressure']) + item['attributes']['pressure_unit']
                self.weather_pressure = pressure
                wind_speed = str(item['attributes']['wind_speed']) + item['attributes']['wind_speed_unit']
                wind_arrow = calc_wind_arrow(int(item['attributes']['wind_bearing']))
                wind = wind_speed + ' ' + wind_arrow + str(int(item['attributes']['wind_bearing']))
                self.weather_wind = wind
            if item['entity_id'] == 'sensor.air_detector_battery':
                self.air_detector_battery = str(int(float(item['state']))) + '%'
            if item['entity_id'] == 'sensor.air_detector_carbon_dioxide':
                self.air_detector_carbon_dioxide = item['state'] + item['attributes']['unit_of_measurement']
            if item['entity_id'] == 'sensor.air_detector_formaldehyde':
                self.air_detector_formaldehyde = item['state'] + item['attributes']['unit_of_measurement']
            if item['entity_id'] == 'sensor.air_detector_humidity':
                self.air_detector_humidity = str(int(float(item['state']))) + '%'
            if item['entity_id'] == 'sensor.air_detector_pm2_5':
                self.air_detector_pm2_5 = item['state'] + item['attributes']['unit_of_measurement']
            if item['entity_id'] == 'sensor.air_detector_temperature':
                self.air_detector_temperature = item['state'] + item['attributes']['unit_of_measurement']
            if item['entity_id'] == 'sensor.air_detector_vocs':
                self.air_detector_vocs = item['state'] + item['attributes']['unit_of_measurement']
            if item['entity_id'] == 'switch.switch_washer':
                self.washer_switch = item['state']
            if item['entity_id'] == 'sensor.washer_1min':
                rounded_reading = float(item['state']) // 1
                self.washer_1min = str(rounded_reading) + 'W'
            if item['entity_id'] == 'sensor.washer_1mon':
                rounded_reading = float(item['state']) // 1
                self.washer_1mon = str(rounded_reading) + 'KWh'
                washer_cost = round(rounded_reading * 0.092, 2)
                self.washer_cost_1mon = "$" + str(washer_cost)
            if item['entity_id'] == 'sensor.washer_1mon':
                rounded_reading = float(item['state']) // 1
                self.washer_1mon = str(rounded_reading) + 'KWh'
            if item['entity_id'] == 'switch.switch_dryer':
                self.dryer_switch = item['state']
            if item['entity_id'] == 'sensor.dryer_1min':
                rounded_reading = float(item['state']) // 1
                self.dryer_1min = str(rounded_reading) + 'W'
            if item['entity_id'] == 'sensor.dryer_1mon':
                rounded_reading = float(item['state']) // 1
                self.dryer_1mon = str(rounded_reading) + 'KWh'
                dryer_cost = round(rounded_reading * 0.092, 2)
                self.dryer_cost_1mon = "$" + str(dryer_cost)
            if item['entity_id'] == 'sensor.beastnas_plex':
                self.plex_stream_count = item['state']
            if item['entity_id'] == 'sensor.sabnzbd_status':
                self.sab_status = item['state']
            if item['entity_id'] == 'number.sabnzbd_speedlimit':
                self.sab_speedlimit = item['state']
            if item['entity_id'] == 'sensor.sabnzbd_speed':
                speed = str(round(float(item['state']), 1))
                unit = item['attributes']['unit_of_measurement']
                self.sab_speed = f'{speed} {unit}'
            if item['entity_id'] == 'sensor.sabnzbd_queue_count':
                self.sab_queue = item['state']
            if item['entity_id'] == 'sensor.sabnzbd_total_disk_space':
                total_disk = round(float(item['state']) / 1000, 2)
                self.sab_total_disk = total_disk
            if item['entity_id'] == 'sensor.sabnzbd_free_disk_space':
                rounded_reading = round(float(item['state']) / 1000, 2)
                rounded_reading_str = str(rounded_reading)
                total_disk_str = str(self.sab_total_disk)
                self.nas_free_disk = f'{rounded_reading_str}/{total_disk_str}TB'
            if item['entity_id'] == 'sensor.deluge_download_speed':
                self.deluge_download_speed = item['state'] + item['attributes']['unit_of_measurement']
            if item['entity_id'] == 'sensor.deluge_upload_speed':
                self.deluge_upload_speed = item['state'] + item['attributes']['unit_of_measurement']
            if item['entity_id'] == 'sensor.deluge_status':
                self.deluge_status = item['state']
            if item['entity_id'] == 'sensor.canon_lbp632c_canon_cartridge_067_black_toner':
                self.printer_black_toner = item['state'] + '%'
            if item['entity_id'] == 'sensor.canon_lbp632c_canon_cartridge_067_cyan_toner':
                self.printer_cyan_toner = item['state'] + '%'
            if item['entity_id'] == 'sensor.canon_lbp632c_canon_cartridge_067_magenta_to':
                self.printer_magenta_toner = item['state'] + '%'
            if item['entity_id'] == 'sensor.canon_lbp632c_canon_cartridge_067_yellow_ton':
                self.printer_yellow_toner = item['state'] + '%'
            if item['entity_id'] == 'switch.main_tv':
                self.main_tv_status = item['state']
            if item['entity_id'] == 'switch.fan':
                self.fan_switch = item['state']
            if item['entity_id'] == 'switch.living_room_nw_corner':
                self.living_room_lights_nw_corner = item['state']
            if item['entity_id'] == 'switch.living_room_sw_corner':
                self.living_room_lights_sw_corner = item['state']
            if item['entity_id'] == 'switch.air_filter':
                self.air_filter = item['state']
            if item['entity_id'] == 'automation.notify_when_laundry_washer_is_done':
                initial_timestamp = item['attributes']['last_triggered']
                chicago_time = convert_to_central_time(initial_timestamp)
                timestamp = chicago_time.isoformat().split('.')[0]
                self.washer_done_last_fired = timestamp
            if item['entity_id'] == 'automation.notify_when_laundry_dryer_is_done':
                initial_timestamp = item['attributes']['last_triggered']
                chicago_time = convert_to_central_time(initial_timestamp)
                timestamp = chicago_time.isoformat().split('.')[0]
                self.dryer_done_last_fired = timestamp
            if item['entity_id'] == 'calendar.united_states_mo':
                holiday = item['attributes']['message']
                holiday_start = item['attributes']['start_time']
                holiday_start_trim = holiday_start.split(' ')[0]
                if self.today_date == holiday_start_trim:
                    holiday_flashy = f"* {holiday} *"
                    holiday_trim = holiday_flashy[0:MAX_WIDTH]
                    self.holiday = holiday_trim
            if item['entity_id'] == 'vacuum.roomba':
                self.roomba_status = item['state']
                self.roomba_battery = str(item['attributes']['battery_level']) + '%'
                self.roomba_bin_full = item['attributes']['bin_full']

    def refresh_router_updates(self, KEY, SECRET):
        self.router_status = 'HEALTHY'
        self.router_updates = 0
        url = 'https://router.mccormicom.com/api/core/firmware/upgradestatus'
        try:
            req = requests.post(url, auth=(KEY, SECRET), verify=False)
            jd = json.loads(req.text)
            for line in jd['log'].split('\n'):
                if 'package(s) will be affected' in line:
                    self.router_updates = line.split(' ')[2]
        except ConnectionError:
            self.router_status = 'DOWN'
            return

        # Kick off a firmware upgrade check. It will take a minute but we'll parse the results next execution.
        url = 'https://router.mccormicom.com/api/core/firmware/check'
        req = requests.post(url, auth=(KEY, SECRET), verify=False)

    def refresh_plex(self, PLEX_TOKEN, HA_TOKEN):
        self.plex_status = 'HEALTHY'
        self.plex_streams = []
        self.plex_new_movies = []
        self.plex_new_episodes = []
        self.refresh_plex_streams(PLEX_TOKEN)
        if self.plex_status == 'DOWN':
            log.warning('Plex is DOWN!')
            self.say_plex_is_down(HA_TOKEN)
        else:
            self.refresh_plex_recently_added(PLEX_TOKEN)

    def refresh_plex_recently_added(self, PLEX_TOKEN):
        if len(self.plex_streams) > 4:
            return
        headers = {'X-Plex-Token': PLEX_TOKEN}
        try:
            plex_recently_added_xml = requests.get(self.PLEX_API + 'library/sections/2/newest', headers=headers)
        except ConnectionError:
            self.plex_status = 'DOWN'
            return
        tv_xml = ElementTree.fromstring(plex_recently_added_xml.text)

        tvshows = []
        for item in tv_xml:
            new_episode = {}
            new_episode['season_name'] = item.attrib['parentTitle'].replace('Season ', 'S')
            new_episode['episode_number'] = item.attrib['index']
            if 'updatedAt' in item.attrib.keys():
                new_episode['epoch_updated'] = item.attrib['updatedAt']
            new_episode['epoch_added'] = item.attrib['addedAt']
            new_episode['show_name'] = item.attrib['grandparentTitle']
            tvshows.append(new_episode)

        try:
            plex_recently_added_xml = requests.get(self.PLEX_API + 'library/sections/1/newest', headers=headers)
        except ConnectionError:
            self.plex_status = 'DOWN'
            return
        movie_xml = ElementTree.fromstring(plex_recently_added_xml.text)

        movies = []
        for item in movie_xml:
            new_movie = {}
            new_movie['title'] = item.attrib['title']
            new_movie['year'] = item.attrib['year']
            new_movie['epoch_added'] = item.attrib['addedAt']
            movies.append(new_movie)

        movies = sorted(movies, key=lambda d: d['epoch_added'], reverse=True)
        tvshows = sorted(tvshows, key=lambda d: d['epoch_added'], reverse=True)

        if len(movies) == 0:
            self.plex_new_movies = []
        elif len(movies) == 1:
            new_movie = movies[0]['year'] + ' ' + movies[0]['title']
            self.plex_new_movies = new_movie[0:MAX_WIDTH]
        elif len(movies) == 2:
            new_movie = movies[0]['year'] + ' ' + movies[0]['title']
            new_movie2 = movies[1]['year'] + ' ' + movies[1]['title']
            self.plex_new_movies = new_movie[0:MAX_WIDTH] + '\n' + new_movie2[0:MAX_WIDTH]
        else:
            new_movie = movies[0]['year'] + ' ' + movies[0]['title']
            new_movie2 = movies[1]['year'] + ' ' + movies[1]['title']
            new_movie3 = movies[2]['year'] + ' ' + movies[2]['title']
            self.plex_new_movies = new_movie[0:MAX_WIDTH] + '\n' + new_movie2[0:MAX_WIDTH] + '\n' + new_movie3[0:MAX_WIDTH]
        if len(tvshows) == 0:
            self.plex_new_episodes = []
        elif len(tvshows) == 1:
            new_episode =  tvshows[0]['show_name'] + ' ' + tvshows[0]['season_name'] + 'E' + tvshows[0]['episode_number']
            self.plex_new_episodes = new_episode[0:MAX_WIDTH]
        elif len(tvshows) == 2:
            new_episode =  tvshows[0]['show_name'] + ' ' + tvshows[0]['season_name'] + 'E' + tvshows[0]['episode_number']
            new_episode2 = tvshows[1]['show_name'] + ' ' + tvshows[1]['season_name'] + 'E' + tvshows[1]['episode_number']
            self.plex_new_episodes = new_episode[0:MAX_WIDTH] + '\n' + new_episode2[0:MAX_WIDTH]
        else:
            new_episode =  tvshows[0]['show_name'] + ' ' + tvshows[0]['season_name'] + 'E' + tvshows[0]['episode_number']
            new_episode2 = tvshows[1]['show_name'] + ' ' + tvshows[1]['season_name'] + 'E' + tvshows[1]['episode_number']
            new_episode3 = tvshows[2]['show_name'] + ' ' + tvshows[2]['season_name'] + 'E' + tvshows[2]['episode_number']
            self.plex_new_episodes = new_episode[0:MAX_WIDTH] + '\n' + new_episode2[0:MAX_WIDTH] + '\n' + new_episode3[0:MAX_WIDTH]

    def refresh_plex_streams(self, PLEX_TOKEN):
        headers = {'X-Plex-Token': PLEX_TOKEN}
        try:
            plex_sessions_xml = requests.get(self.PLEX_API + 'status/sessions', headers=headers)
        except ConnectionError:
            self.plex_status = 'DOWN'
            return
        xml_tree = ElementTree.fromstring(plex_sessions_xml.text)
        streams = []
        for stream in xml_tree:
            stream_item = {}
            stream_item['type'] = stream.attrib['type']
            stream_item['title'] = stream.attrib['title']
            if 'parentTitle' in stream.attrib.keys():
                if stream_item['type'] == 'episode':
                    stream_item['season'] = stream.attrib['parentTitle']
                elif stream_item['type'] == 'track':
                    stream_item['album'] = stream.attrib['parentTitle']
            if 'grandparentTitle' in stream.attrib.keys():
                if stream_item['type'] == 'episode':
                    stream_item['tv_show'] = stream.attrib['grandparentTitle']
                elif stream_item['type'] == 'track':
                    stream_item['artist'] = stream.attrib['grandparentTitle']
                else:
                    stream_item['grandparent'] = stream.attrib['grandparentTitle']
            for child in stream:
                if child.tag == 'User' and 'title' in child.attrib.keys():
                    stream_item['user'] = child.attrib['title']
                if child.tag == 'Media' and 'videoResolution' in child.attrib.keys():
                    stream_item['video_resolution'] = child.attrib['videoResolution']
                if child.tag == 'Session' and 'location' in child.attrib.keys():
                    stream_item['location'] = child.attrib['location']
                if child.tag == 'Player' and 'state' in child.attrib.keys():
                    stream_item['state'] = child.attrib['state']
                if child.tag == 'Player' and 'remotePublicAddress' in child.attrib.keys():
                    remote_ip = child.attrib['remotePublicAddress']
                    if '127.0.0.1' not in remote_ip and '192.168.' not in remote_ip:
                        stream_item['ip'] = remote_ip
            streams.append(stream_item)
        clean_streams = []
        for stream in streams:
            if stream['type'] == 'track':
                s = f"{stream['user']} \u266c {stream['artist']}."
                clean_streams.append(s[0:MAX_WIDTH])
            elif stream['type'] == 'movie':
                s = f"{stream['user']} \u2680 {stream['title']}."
                clean_streams.append(s[0:MAX_WIDTH])
            elif stream['type'] == 'episode':
                season = stream['season'].replace('Season ', 'S')
                s = f"{stream['user']} \u30ed {stream['tv_show']} {season}."
                clean_streams.append(s[0:MAX_WIDTH])
        self.plex_streams = clean_streams

    def refresh_worldweather(self, WEATHER_TOKEN):
        self.timestamp = datetime.now().isoformat().split('.')[0]
        self.today_date = self.timestamp.split('T')[0]
        tomorrow_timestamp = datetime.now() + timedelta(days=1)
        self.tomorrow_timestamp = tomorrow_timestamp.isoformat().split('.')[0]
        self.tomorrow_date = self.tomorrow_timestamp.split('T')[0]
        plus_2_timestamp = datetime.now() + timedelta(days=2)
        self.plus_2_timestamp = plus_2_timestamp.isoformat().split('.')[0]
        self.plus_2_date = self.plus_2_timestamp.split('T')[0]
        plus_3_timestamp = datetime.now() + timedelta(days=3)
        self.plus_3_timestamp = plus_3_timestamp.isoformat().split('.')[0]
        self.plus_3_date = self.plus_3_timestamp.split('T')[0]

        zipcode = 63021
        url = f'https://api.worldweatheronline.com/premium/v1/weather.ashx?key={WEATHER_TOKEN}&q={zipcode}'
        resp = requests.request('GET', url)
        if resp.status_code == 429:
            log.error('WorldWeather API calls used up for the day.')
            return
        xml_data = ElementTree.fromstring(resp.text)

        for branch in xml_data:
            if branch.tag == 'weather':
                for branch_l2 in branch:
                    if branch_l2.tag == 'date' and branch_l2.text == self.today_date:
                        today_weather = branch
                    elif branch_l2.tag == 'date' and branch_l2.text == self.tomorrow_date:
                        tomorrow_weather = branch
                    elif branch_l2.tag == 'date' and branch_l2.text == self.plus_2_date:
                        plus_2_weather = branch
                    elif branch_l2.tag == 'date' and branch_l2.text == self.plus_3_date:
                        plus_3_weather = branch
        for branch in today_weather:
            if branch.tag == 'mintempF':
                self.today_low_temp = branch.text
            if branch.tag == 'maxtempF':
                self.today_high_temp = branch.text
            if branch.tag == 'sunHour':
                self.today_sunhours = branch.text
        for branch in tomorrow_weather:
            if branch.tag == 'mintempF':
                self.tomorrow_low_temp = branch.text
            if branch.tag == 'maxtempF':
                self.tomorrow_high_temp = branch.text
            if branch.tag == 'sunHour':
                self.tomorrow_sunhours = branch.text
        for branch in plus_2_weather:
            if branch.tag == 'mintempF':
                self.plus_2_low_temp = branch.text
            if branch.tag == 'maxtempF':
                self.plus_2_high_temp = branch.text
            if branch.tag == 'sunHour':
                self.plus_2_sunhours = branch.text
        for branch in plus_3_weather:
            if branch.tag == 'mintempF':
                self.plus_3_low_temp = branch.text
            if branch.tag == 'maxtempF':
                self.plus_3_high_temp = branch.text
            if branch.tag == 'sunHour':
                self.plus_3_sunhours = branch.text

    def draw(self):
        font16 = ImageFont.truetype('Font.ttc', 16)
        font18 = ImageFont.truetype('Font.ttc', 18)
        font24 = ImageFont.truetype('Font.ttc', 24)
        font40 = ImageFont.truetype('Font.ttc', 40)
        self.timestamp = datetime.now().isoformat().split('.')[0]

        # Drawing on the Horizontal image
        Himage = Image.new('RGB', (self.epd.width, self.epd.height), 0xffffff)  # 255: clear the frame
        draw = ImageDraw.Draw(Himage)
        # Draw the container boxes
        draw.rounded_rectangle((0, 0, 200, 220),     outline = self.epd.ORANGE, width=2)
        draw.rounded_rectangle((200, 0, 400, 220),   outline = self.epd.GREEN,  width=2)
        draw.rounded_rectangle((400, 0, 599, 220),   outline = self.epd.BLUE,   width=2)
        draw.rounded_rectangle((0, 220, 200, 447),   outline = self.epd.BLUE,   width=2)
        draw.rounded_rectangle((200, 220, 400, 447), outline = self.epd.RED,    width=2)
        draw.rounded_rectangle((400, 220, 599, 447), outline = self.epd.YELLOW, width=2)
        # Draw the top-left box for weather stuff.
        draw.text((2, 0), f'\u21ba {self.timestamp}',           font=font18, fill=0)
        draw.text((2, 20), f'Sunrise: {self.next_dawn}',        font=font18, fill=0)
        draw.text((2, 40), f'Sunset: {self.next_dusk}',         font=font18, fill=0)
        draw.text((2, 60), f'Weather: {self.weather}',          font=font18, fill=0)
        draw.text((2, 80), f'Temp: {self.weather_temperature}', font=font18, fill=0)
        draw.text((105, 80), f'Hum: {self.weather_humidity}',   font=font18, fill=0)
        draw.text((2, 100), f'TD', font=font18, fill=0)
        draw.text((28, 100), f'{self.today_high_temp}/{self.today_low_temp}\u00b0F', font=font18, fill=self.epd.GREEN)
        draw.text((105, 100), f'TM {self.tomorrow_high_temp}/{self.tomorrow_low_temp}\u00b0F', font=font18, fill=0)
        draw.text((2, 120), f'+2 {self.plus_2_high_temp}/{self.plus_2_low_temp}\u00b0F    +3 {self.plus_3_high_temp}/{self.plus_3_low_temp}\u00b0F', font=font18, fill=0)
        draw.text((2, 140), f'UV Index: {self.weather_uv_index}', font=font18, fill=0)
        draw.text((2, 160), f'Pressure: {self.weather_pressure}', font=font18, fill=0)
        draw.text((2, 180), f'Wind: {self.weather_wind}',         font=font18, fill=0)
        # Draw the top middle box for printer and router stuff.
        draw.text((204, 0), f'Printer Black: {self.printer_black_toner}',      font=font18, fill=0)
        draw.text((204, 20), f'Printer Cyan: {self.printer_cyan_toner}',       font=font18, fill=0)
        draw.text((204, 40), f'Printer Magenta: {self.printer_magenta_toner}', font=font18, fill=0)
        draw.text((204, 60), f'Printer Yellow: {self.printer_yellow_toner}',   font=font18, fill=0)
        if self.router_status == 'HEALTHY':
            draw.text((204, 100), f'Router Updates: {self.router_updates}',     font=font18, fill=0)
        draw.text((204, 140), f'Roomba is {self.roomba_status}',               font=font18, fill=0)
        draw.text((204, 160), f'BAT {self.roomba_battery} FULL {self.roomba_bin_full}', font=font18, fill=0)
        if self.holiday:
            draw.text((204, 200), f'{self.holiday}',                           font=font18, fill=0)
        # Draw the top right box for downloader stuff.
        draw.text((406, 0), f'SAB Status: {self.sab_status}',            font=font18, fill=0)
        draw.text((406, 20), f'SAB Queue: {self.sab_queue}',             font=font18, fill=0)
        draw.text((406, 40), f'SAB Speed: {self.sab_speed}',             font=font18, fill=0)
        draw.text((406, 60), f'SAB Speedlimit: {self.sab_speedlimit}',   font=font18, fill=0)
        draw.text((406, 100), 'Deluge',                                  font=font18, fill=0)
        draw.text((406, 120), f'{self.deluge_status}',                   font=font18, fill=0)
        draw.text((406, 140), f'Download: {self.deluge_download_speed}', font=font18, fill=0)
        draw.text((406, 160), f'Upload: {self.deluge_upload_speed}',     font=font18, fill=0)
        draw.text((406, 180), f'Free Disk: {self.nas_free_disk}',        font=font18, fill=0)
        # Draw the bottom left box for laundry stuff.
        draw.text((2, 222), f'Washer: {self.washer_switch}',         font = font18, fill = 0)
        draw.text((2, 242), f'Usage: {self.washer_1min}/minute',     font = font18, fill = 0)
        draw.text((2, 262), f'Usage: {self.washer_1mon}/month',      font = font18, fill = 0)
        draw.text((2, 282), f'Cost: {self.washer_cost_1mon}/month',  font = font18, fill = 0)
        draw.text((2, 302), f'\u2713 {self.washer_done_last_fired}', font = font18, fill = 0)
        draw.text((2, 342), f'Dryer: {self.dryer_switch}',           font = font18, fill = 0)
        draw.text((2, 362), f'Usage: {self.dryer_1min}/minute',      font = font18, fill = 0)
        draw.text((2, 382), f'Usage: {self.dryer_1mon}/month',       font = font18, fill = 0)
        draw.text((2, 402), f'Cost: {self.dryer_cost_1mon}/month',   font = font18, fill = 0)
        draw.text((2, 422), f'\u2713 {self.dryer_done_last_fired}',  font = font18, fill = 0)
        # Draw the bottom middle box for Plex stuff.
        draw.text((204, 222), f'Plex', font=font18, fill=0)
        if self.plex_status == 'HEALTHY':
            index = 222
            for stream in self.plex_streams:
                index += 20
                draw.text((204, index), f'{stream}', font=font18, fill=0)
            if len(self.plex_streams) == 0:
                index = 242
            elif len(self.plex_streams) == 1:
                index = 262
            elif len(self.plex_streams) == 2:
                index = 282
            elif len(self.plex_streams) == 3:
                index = 302

            if self.plex_new_movies:
                draw.text((204, index), f'New Movies:', font=font18, fill=0)
                index += 20
                draw.text((204, index), f'{self.plex_new_movies}', font=font18, fill=0)
            if self.plex_new_episodes:
                index += 60
                draw.text((204, index), f'New Episodes:', font=font18, fill=0)
                index += 20
                draw.text((204, index), f'{self.plex_new_episodes}', font=font18, fill=0)
        else:
            index = 242
            draw.text((204, index), f'Plex is DOWN!', font=font18, fill=self.epd.RED)

        # Draw the bottom right box for Indoor Climate and Air Quality stuff.
        draw.text((406, 222), f'Indoor Climate and Air', font = font18, fill = 0)
        draw.text((406, 242), f'Battery: {self.air_detector_battery}', font = font18, fill = 0)
        draw.text((406, 262), f'Temperature: {self.air_detector_temperature}', font = font18, fill = 0)
        draw.text((406, 282), f'Humidity: {self.air_detector_humidity}', font = font18, fill = 0)
        draw.text((406, 302), f'CO2: {self.air_detector_carbon_dioxide}', font = font18, fill = 0)
        draw.text((406, 322), f'Formald: {self.air_detector_formaldehyde}', font = font18, fill = 0)
        draw.text((406, 342), f'VOCS: {self.air_detector_vocs}', font = font18, fill = 0)
        draw.text((406, 362), f'PM2.5: {self.air_detector_pm2_5}', font = font18, fill = 0)

        self.epd.display(self.epd.getbuffer(Himage))

        log.debug("Put screen driver to sleep...")
        self.epd.sleep()

if __name__ == "__main__":
    main()
