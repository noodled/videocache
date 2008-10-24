#!/usr/bin/env python

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# (C) Copyright 2008 Kulbir Saini <kulbirsaini@students.iiit.ac.in>
#
# For configuration and how to use, see README file.
#

__author__ = """Kulbir Saini <kulbirsaini@students.iiit.ac.in>"""
__version__ = 0.1
__docformat__ = 'plaintext'

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from config import readMainConfig, readStartupConfig
import logging
import logging.handlers
import md5
import os
import re
import stat
import sys
import time
import urlgrabber
import urllib2
import urlparse
from xmlrpclib import ServerProxy
from SimpleXMLRPCServer import SimpleXMLRPCServer

mainconf =  readMainConfig(readStartupConfig('/etc/youtube_cache.conf', '/'))

# Gloabl Options
base_dir = mainconf.base_dir
temp_dir = os.path.join(base_dir, mainconf.temp_dir)
max_parallel_downloads = int(mainconf.max_parallel_downloads)
cache_host = mainconf.cache_host
rpc_host = mainconf.rpc_host
rpc_port = int(mainconf.rpc_port)
logfile = mainconf.logfile
max_logfile_size = int(mainconf.max_logfile_size) * 1024 * 1024
max_logfile_backups = int(mainconf.max_logfile_backups)
proxy = mainconf.proxy
proxy_username = mainconf.proxy_username
proxy_password = mainconf.proxy_password

redirect = '303'
format = '%s %s %s %s %s'
cache_url = 'http://' + str(cache_host) + '/' 

# Youtube specific options
enable_youtube_cache = int(mainconf.enable_youtube_cache)
youtube_cache_dir = os.path.join(base_dir, mainconf.youtube_cache_dir)
youtube_cache_size = int(mainconf.youtube_cache_size)
max_youtube_video_size = int(mainconf.max_youtube_video_size)
min_youtube_video_size = int(mainconf.min_youtube_video_size)

# Metacafe specific options
enable_metacafe_cache = int(mainconf.enable_metacafe_cache)
metacafe_cache_dir = os.path.join(base_dir, mainconf.metacafe_cache_dir)
metacafe_cache_size = int(mainconf.metacafe_cache_size)
max_metacafe_video_size = int(mainconf.max_metacafe_video_size)
min_metacafe_video_size = int(mainconf.min_metacafe_video_size)

# Dailymotion specific options
enable_dailymotion_cache = int(mainconf.enable_dailymotion_cache)
dailymotion_cache_dir = os.path.join(base_dir, mainconf.dailymotion_cache_dir)
dailymotion_cache_size = int(mainconf.dailymotion_cache_size)
max_dailymotion_video_size = int(mainconf.max_dailymotion_video_size)
min_dailymotion_video_size = int(mainconf.min_dailymotion_video_size)

# Google.com specific options
enable_google_cache = int(mainconf.enable_google_cache)
google_cache_dir = os.path.join(base_dir, mainconf.google_cache_dir)
google_cache_size = int(mainconf.google_cache_size)
max_google_video_size = int(mainconf.max_google_video_size)
min_google_video_size = int(mainconf.min_google_video_size)

# Redtube.com specific options
enable_redtube_cache = int(mainconf.enable_redtube_cache)
redtube_cache_dir = os.path.join(base_dir, mainconf.redtube_cache_dir)
redtube_cache_size = int(mainconf.redtube_cache_size)
max_redtube_video_size = int(mainconf.max_redtube_video_size)
min_redtube_video_size = int(mainconf.min_redtube_video_size)

# Xtube.com specific options
enable_xtube_cache = int(mainconf.enable_xtube_cache)
xtube_cache_dir = os.path.join(base_dir, mainconf.xtube_cache_dir)
xtube_cache_size = int(mainconf.xtube_cache_size)
max_xtube_video_size = int(mainconf.max_xtube_video_size)
min_xtube_video_size = int(mainconf.min_xtube_video_size)

# Vimeo.com specific options
enable_vimeo_cache = int(mainconf.enable_vimeo_cache)
vimeo_cache_dir = os.path.join(base_dir, mainconf.vimeo_cache_dir)
vimeo_cache_size = int(mainconf.vimeo_cache_size)
max_vimeo_video_size = int(mainconf.max_vimeo_video_size)
min_vimeo_video_size = int(mainconf.min_vimeo_video_size)

def set_proxy():
    if proxy_username and proxy_password:
        proxy_parts = urlparse.urlsplit(proxy)
        new_proxy = '%s://%s:%s@%s/' % (proxy_parts[0], proxy_username, proxy_password, proxy_parts[1])
    else:
        new_proxy = proxy
    return urlgrabber.grabber.URLGrabber(proxies = {'http': new_proxy})

def set_logging():
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s %(levelname)s %(message)s',
                        filename=logfile,
                        filemode='a')
    return logging.info

def dir_size(dir):
    """
    This is not a standard function to calculate the size of a directory.
    This function will only give the sum of sizes of all the files in 'dir'.
    """
    # Initialize with 4096bytes as the size of an empty dir is 4096bytes.
    size = 4096
    try:
        for file in os.listdir(dir):
            size += int(os.stat(os.path.join(dir, file))[6])
    except:
        return -1
    return size / (1024*1024)

class VideoIDPool:
    """
    This class is for sharing the current packages being downloading
    across various instances of intelligentmirror via XMLRPC.
    """
    def __init__(self):
        self.scores = {}
        self.queue = {}
        self.active = []
        pass

    # Function related to video_id queue-ing.
    def add(self, video_id, score = 1):
        """Queue a video_id for download. Score defaults to zero."""
        if video_id not in self.queue.keys():
            self.queue[video_id] = []
        self.scores[video_id] = score
        return

    def set(self, video_id, values):
        """Set the details of video_id to values."""
        self.queue[video_id] = values
        return

    def set_score(self, video_id, score = 0):
        """Set the priority score of a video_id."""
        self.scores[video_id] = score
        return

    def inc_score(self, video_id, incr = 1):
        """Increase the priority score of video represented by video_id."""
        if video_id in self.scores.keys():
            self.scores[video_id] += incr
        return

    def get(self):
        """Return all the video ids currently in queue."""
        return self.queue.keys()

    def get_details(self, video_id):
        """Return the details of a particular video represented by video_id."""
        if video_id in self.queue.keys():
            return self.queue[video_id]
        return None

    def get_popular(self):
        """Return the video_id of the most frequently access video."""
        vk = [(v,k) for k,v in self.scores.items()]
        if len(vk) != 0:
            video_id = sorted(vk, reverse=True)[0][1]
            return video_id
        return None

    def remove(self, video_id):
        """Dequeue a video_id from the download queue."""
        if video_id in self.queue.keys():
            self.queue.pop(video_id)
        if video_id in self.scores.keys():
            self.scores.pop(video_id)
        return

    def flush(self):
        """Flush the queue and reinitialize everything."""
        self.queue = {}
        self.scores = {}
        self.active = []
        return

    # Functions related download scheduling.
    # Have to mess up things in single class because python
    # XMLRPCServer doesn't allow to register multiple instances
    # via register_instance
    def add_conn(self, video_id):
        """Add video_id to active connections list."""
        if video_id not in self.active:
            self.active.append(video_id)
        return

    def get_conn(self):
        """Return a list of currently active connections."""
        return self.active

    def get_conn_number(self):
        """Return the number of currently active connections."""
        return len(self.active)

    def is_active(self, video_id):
        """Returns whether a connection is active or not."""
        if video_id in self.active:
            return True
        return False

    def remove_conn(self, video_id):
        """Remove video_id from active connections list."""
        if video_id in self.active:
            self.active.remove(video_id)
        return

def remove(video_id):
    """Remove video_id from queue."""
    video_id_pool.remove(video_id)
    video_id_pool.remove_conn(video_id)
    return

def queue(video_id, values):
    """Queue video_id for scheduling later by download_scheduler."""
    video_id_pool.set(video_id, values)
    return

def fork(f):
    """This function is highly inspired from concurrency in python
    tutorial at http://blog.buffis.com/?p=63 .
    Generator for creating a forked process from a function"""
    # Perform double fork
    r = ''
    if os.fork(): # Parent
        # Wait for the child so that it doesn't get defunct
        os.wait()
        # Return a function
        return  lambda *x, **kw: r 

    # Otherwise, we are the child 
    # Perform second fork
    os.setsid()
    os.umask(077)
    os.chdir('/')
    if os.fork():
        os._exit(0) 

    def wrapper(*args, **kwargs):
        """Wrapper function to be returned from generator.
        Executes the function bound to the generator and then
        exits the process"""
        f(*args, **kwargs)
        os._exit(0)

    return wrapper

def download_from_source(args):
    """This function downloads the file from remote source and caches it."""
    client = args[0]
    url = args[1]
    path = args[2]
    mode = args[3]
    video_id = args[4]
    type = args[5]
    max_size = args[6]
    min_size = args[7]
    if max_size or min_size:
        try:
            log(format%(client, video_id, 'GET_SIZE', type, 'Trying to get the size of video.'))
            remote_file = grabber.urlopen(url)
            remote_size = int(remote_file.info().getheader('content-length')) / 1024
            remote_file.close()
            log(format%(client, video_id, 'GOT_SIZE', type, 'Successfully retrieved the size of video.'))
        except urlgrabber.grabber.URLGrabError, e:
            remove(video_id)
            log(format%(client, video_id, 'SIZE_ERR', type, 'Could not retrieve size of the video.'))
            return

        if max_size and remote_size > max_size:
            remove(video_id)
            log(format%(client, video_id, 'MAX_SIZE', type, 'Video size ' + str(remote_size) + ' is larger than maximum allowed.'))
            return
        if min_size and remote_size < min_size:
            remove(video_id)
            log(format%(client, video_id, 'MIN_SIZE', type, 'Video size ' + str(remote_size) + ' is smaller than minimum allowed.'))
            return

    try:
        download_path = os.path.join(temp_dir, md5.md5(os.path.basename(path)).hexdigest())
        open(download_path, 'a').close()
        file = grabber.urlgrab(url, download_path)
        os.rename(file, path)
        os.chmod(path, mode)
        remove(video_id)
        size = os.stat(path)[6]
        log(format%(client, video_id, 'DOWNLOAD', type, str(size) + ' Video was downloaded and cached.'))
    except urlgrabber.grabber.URLGrabError, e:
        remove(video_id)
        log(format%(client, video_id, 'DOWNLOAD_ERR', type, 'An error occured while retrieving the video.'))
        os.unlink(download_path)

    return

def cache_video(client, url, type, video_id):
    """This function check whether a video is in cache or not. If not, it fetches
    it from the remote source and cache it and also streams it to the client."""
    # The expected mode of the cached file, so that it is readable by apache
    # to stream it to the client.
    global cache_url
    mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
    if type == 'YOUTUBE':
        params = urlparse.urlsplit(url)[3]
        path = os.path.join(youtube_cache_dir, video_id) + '.flv'
        cached_url = os.path.join(cache_url, base_dir.strip('/').split('/')[-1], type.lower())
        max_size = max_youtube_video_size
        min_size = min_youtube_video_size
        cache_size = youtube_cache_size
        cache_dir = youtube_cache_dir

    if type == 'METACAFE':
        params = urlparse.urlsplit(url)[3]
        path = os.path.join(metacafe_cache_dir, video_id) + '.flv'
        cached_url = os.path.join(cache_url, base_dir.strip('/').split('/')[-1], type.lower())
        max_size = max_metacafe_video_size
        min_size = min_metacafe_video_size
        cache_size = metacafe_cache_size
        cache_dir = metacafe_cache_dir

    if type == 'DAILYMOTION':
        params = urlparse.urlsplit(url)[3]
        path = os.path.join(dailymotion_cache_dir, video_id) + '.flv'
        cached_url = os.path.join(cache_url, base_dir.strip('/').split('/')[-1], type.lower())
        max_size = max_dailymotion_video_size
        min_size = min_dailymotion_video_size
        cache_size = dailymotion_cache_size
        cache_dir = dailymotion_cache_dir

    if type == 'GOOGLE':
        params = urlparse.urlsplit(url)[3]
        path = os.path.join(google_cache_dir, video_id) + '.flv'
        cached_url = os.path.join(cache_url, base_dir.strip('/').split('/')[-1], type.lower())
        max_size = max_google_video_size
        min_size = min_google_video_size
        cache_size = google_cache_size
        cache_dir = google_cache_dir

    if type == 'REDTUBE':
        params = urlparse.urlsplit(url)[3]
        path = os.path.join(redtube_cache_dir, video_id) + '.flv'
        cached_url = os.path.join(cache_url, base_dir.strip('/').split('/')[-1], type.lower())
        max_size = max_redtube_video_size
        min_size = min_redtube_video_size
        cache_size = redtube_cache_size
        cache_dir = redtube_cache_dir

    if type == 'XTUBE':
        params = urlparse.urlsplit(url)[3]
        path = os.path.join(xtube_cache_dir, video_id) + '.flv'
        cached_url = os.path.join(cache_url, base_dir.strip('/').split('/')[-1], type.lower())
        max_size = max_xtube_video_size
        min_size = min_xtube_video_size
        cache_size = xtube_cache_size
        cache_dir = xtube_cache_dir

    if type == 'VIMEO':
        params = urlparse.urlsplit(url)[3]
        path = os.path.join(vimeo_cache_dir, video_id) + '.flv'
        cached_url = os.path.join(cache_url, base_dir.strip('/').split('/')[-1], type.lower())
        max_size = max_vimeo_video_size
        min_size = min_vimeo_video_size
        cache_size = vimeo_cache_size
        cache_dir = vimeo_cache_dir

    if os.path.isfile(path):
        log(format%(client, video_id, 'CACHE_HIT', type, 'Requested video was found in cache.'))
        cur_mode = os.stat(path)[stat.ST_MODE]
        remove(video_id)
        if stat.S_IMODE(cur_mode) == mode:
            log(format%(client, video_id, 'CACHE_SERVE', type, 'Video was served from cache.'))
            return redirect + ':' + os.path.join(cached_url, video_id) + '.flv?' + params
    elif cache_size == 0 or dir_size(cache_dir) < cache_size:
        log(format%(client, video_id, 'CACHE_MISS', type, 'Requested video was not found in cache.'))
        queue(video_id, [client, url, path, mode, video_id, type, max_size, min_size])
    else:
        log(format%(client, video_id, 'CACHE_FULL', type, 'Cache directory \'' + cache_dir + '\' has exceeded the maximum size allowed.'))

    return url

def squid_part():
    """This function will tap requests from squid. If the request is for a youtube
    video, they will be forwarded to function cache_video() for further processing.
    Finally this function will flush a cache_url if package found in cache or a
    blank line in case on a miss to stdout. This is the only function where we deal
    with squid, rest of the program/project doesn't interact with squid at all."""
    while True:
        try:
            # Read url from stdin ( this is provided by squid)
            url = sys.stdin.readline().strip().split(' ')
            new_url = url[0];
            # Retrieve the basename from the request url
            fragments = urlparse.urlsplit(url[0])
            host = fragments[1]
            path = fragments[2]
            params = fragments[3]
            client = url[1].split('/')[0]
            log(format%(client, '-', 'REQUEST', '-', url[0]))
            # Youtube.com caching is handled here.
            try:
                if enable_youtube_cache:
                    if host.find('youtube.com') > -1 and path.find('get_video') > -1:
                        video_id = params.split('&')[0].split('=')[1]
                        type = 'YOUTUBE'
                        videos = video_id_pool.get()
                        if video_id in videos:
                            video_id_pool.inc_score(video_id)
                            video_id_pool.get_popular()
                            pass
                        else:
                            video_id_pool.add(video_id)
                            log(format%(client, video_id, 'URL_HIT', type, url[0]))
                            new_url = cache_video(client, url[0], type, video_id)
                            log(format%(client, video_id, 'NEW_URL', type, new_url))
            except:
                log(format%(client, '-', 'NEW_URL', 'YOUTUBE', 'Error in parsing the url ' + new_url))
            
            # Metacafe.com caching is handled here.
            try:
                if enable_metacafe_cache:
                    if host.find('v.mccont.com') > -1 and path.find('ItemFiles') > -1:
                        type = 'METACAFE'
                        video_id = urllib2.unquote(path).split(' ')[2].split('.')[0]
                        videos = video_id_pool.get()
                        if video_id in videos:
                            video_id_pool.inc_score(video_id)
                            pass
                        else:
                            video_id_pool.add(video_id)
                            log(format%(client ,video_id, 'URL_HIT', type, url[0]))
                            new_url = cache_video(client, url[0], type, video_id)
                            log(format%(client, video_id, 'NEW_URL', type, new_url))
            except:
                log(format%(client, '-', 'NEW_URL', 'METACAFE', 'Error in parsing the url ' + new_url))

            # Dailymotion.com caching is handled here.
            try:
                if enable_dailymotion_cache:
                    if host.find('dailymotion.com') > -1 and host.find('proxy') > -1 and path.find('on2') > -1:
                        video_id = path.split('/')[-1]
                        type = 'DAILYMOTION'
                        videos = video_id_pool.get()
                        if video_id in videos:
                            video_id_pool.inc_score(video_id)
                            pass
                        else:
                            video_id_pool.add(video_id)
                            log(format%(client, video_id, 'URL_HIT', type, url[0]))
                            new_url = cache_video(client, url[0], type, video_id)
                            log(format%(client ,video_id, 'NEW_URL', type, new_url))
            except:
                log(format%(client, '-', 'NEW_URL', 'DAILYMOTION', 'Error in parsing the url ' + new_url))
            
            # Google.com caching is handled here.
            try:
                if enable_google_cache:
                    if host.find('vp.video.google.com') > -1 and path.find('videodownload') > -1:
                        video_id = params.split('&')[-1].split('=')[-1]
                        type = 'GOOGLE'
                        videos = video_id_pool.get()
                        if video_id in videos:
                            video_id_pool.inc_score(video_id)
                            pass
                        else:
                            video_id_pool.add(video_id)
                            log(format%(client, video_id, 'URL_HIT', type, url[0]))
                            new_url = cache_video(client, url[0], type, video_id)
                            log(format%(client, video_id, 'NEW_URL', type, new_url))
            except:
                log(format%(client, '-', 'NEW_URL', 'GOOGLE', 'Error in parsing the url ' + new_url))
            
            # Redtube.com caching is handled here.
            try:
                if enable_redtube_cache:
                    if host.find('dl.redtube.com') > -1 and path.find('.flv') > -1:
                        video_id = path.strip('/').split('/')[-1].replace('.flv','')
                        type = 'REDTUBE'
                        videos = video_id_pool.get()
                        if video_id in videos:
                            video_id_pool.inc_score(video_id)
                            pass
                        else:
                            video_id_pool.add(video_id)
                            log(format%(client, video_id, 'URL_HIT', type, url[0]))
                            new_url = cache_video(client, url[0], type, video_id)
                            log(format%(client, video_id, 'NEW_URL', type, new_url))
            except:
                log(format%(client, '-', 'NEW_URL', 'REDTUBE', 'Error in parsing the url ' + new_url))
            
            # Xtube.com caching is handled here.
            try:
                if enable_xtube_cache:
                    if re.compile('p[0-9a-z][0-9a-z]?[0-9a-z]?\.xtube\.com').match(host) and path.find('videos/') > -1 and path.find('.flv') > -1:
                        video_id = path.strip('/').split('/')[-1].replace('.flv','')
                        type = 'XTUBE'
                        videos = video_id_pool.get()
                        if video_id in videos:
                            video_id_pool.inc_score(video_id)
                            pass
                        else:
                            video_id_pool.add(video_id)
                            log(format%(client, video_id, 'URL_HIT', type, url[0]))
                            new_url = cache_video(client, url[0], type, video_id)
                            log(format%(client, video_id, 'NEW_URL', type, new_url))
            except:
                log(format%(client, '-', 'NEW_URL', 'XTUBE', 'Error in parsing the url ' + new_url))
            
            # Vimeo.com caching is handled here.
            try:
                if enable_vimeo_cache:
                    if host.find('bitcast.vimeo.com') > -1 and path.find('vimeo/videos/') > -1 and path.find('.flv') > -1:
                        video_id = path.strip('/').split('/')[-1].replace('.flv','')
                        type = 'VIMEO'
                        videos = video_id_pool.get()
                        if video_id in videos:
                            video_id_pool.inc_score(video_id)
                            pass
                        else:
                            video_id_pool.add(video_id)
                            log(format%(client, video_id, 'URL_HIT', type, url[0]))
                            new_url = cache_video(client, url[0], type, video_id)
                            log(format%(client, video_id, 'NEW_URL', type, new_url))
            except:
                log(format%(client, '-', 'NEW_URL', 'VIMEO', 'Error in parsing the url ' + new_url))
            
            # Flush the new url to stdout for squid to process
            sys.stdout.write(new_url + '\n')
            sys.stdout.flush()
        except:
            file = open('/var/log/squid/youtube.pid', 'r')
            pid = int(file.read().strip('\n'))
            file.close()
            os.kill(pid, 9)

def start_xmlrpc_server():
    """Starts the XMLRPC server in a forked daemon process."""
    server = SimpleXMLRPCServer((rpc_host, rpc_port), logRequests=0, allow_none=True)
    server.register_instance(VideoIDPool())
    log(format%('-', '-', 'XMLRPCServer', '-', 'Starting XMLRPCServer on port ' + str(rpc_port) + '.'))
    file = open('/var/log/squid/youtube.pid', 'w')
    file.write(str(os.getpid()))
    file.close()
    # Rotate logfiles if the size is more than the max_logfile_size.
    if os.stat(logfile)[6] > max_logfile_size:
        roll = logging.handlers.RotatingFileHandler(filename=logfile, mode='r', maxBytes=max_logfile_size, backupCount=max_logfile_backups)
        roll.doRollover()
    server.serve_forever()

def download_scheduler():
    """Schedule videos from download queue for downloading."""
    file = open('/var/log/squid/youtube.pid', 'r')
    pid = int(file.read().strip('\n'))
    file.close()
    while True:
        file = open('/var/log/squid/youtube.pid', 'r')
        new_pid = int(file.read().strip('\n'))
        file.close()
        # If the XMLRPCServer PID has changed, that means squid service was reloaded
        if new_pid != pid:
            return
        video_id_pool = ServerProxy('http://' + rpc_host + ':' + str(rpc_port))
        if video_id_pool.get_conn_number() < max_parallel_downloads:
            video_id = video_id_pool.get_popular()
            if video_id != None and video_id_pool.is_active(video_id) == False:
                video_id_pool.set_score(video_id)
                video_id_pool.add_conn(video_id)
                params = video_id_pool.get_details(video_id)
                if params is not None:
                    log(format%(params[0], params[4], 'SCHEDULED', params[5], 'Video scheduled for download.'))
                    forked = fork(download_from_source)
                    forked(params)
        time.sleep(3)
    return

if __name__ == '__main__':
    global grabber, log, video_id_pool
    grabber = set_proxy()
    log = set_logging()

    # If XMLRPCServer is running already, don't start it again
    try:
        video_id_pool = ServerProxy('http://' + rpc_host + ':' + str(rpc_port))
        list = video_id_pool.get()
        # Flush previous values on reload
        video_id_pool.flush()
    except:
        # Start XMLRPCServer in a forked daemon
        forked = fork(start_xmlrpc_server)
        forked()
        video_id_pool = ServerProxy('http://' + rpc_host + ':' + str(rpc_port))
        list = video_id_pool.get()
        # Flush previous values on reload
        video_id_pool.flush()
        download_scheduler()
        sys.exit(0)

    # For testing with squid, use this function
    squid_part()

