import re
import os
import html
import logging
from .models import Library
from .dbaccess import DBAccess as dbxs
from datetime import datetime
from django.utils import timezone
from mimetypes import guess_type, guess_extension
from django.conf import settings
from vinanti import Vinanti

logger = logging.getLogger(__name__)

class ImportBookmarks:
    
    vnt = Vinanti(block=False,
                  hdrs={'User-Agent':settings.USER_AGENT},
                  max_requests=20)
    
    @classmethod
    def import_bookmarks(cls, usr, settings_row, import_file, mode='file'):
        book_dict = cls.convert_bookmark_to_dict(import_file, mode=mode)
        insert_links_list = []
        insert_dir_list = []
        url_list = []
        for dirname in book_dict:
            if '/' in dirname or ':' in dirname:
                dirname = re.sub(r'/|:', '-', dirname)
            if dirname:
                qdir = Library.objects.filter(usr=usr, directory=dirname)
                if not qdir:
                    dirlist = Library(usr=usr, directory=dirname, timestamp=timezone.now())
                    insert_dir_list.append(dirlist)
        if insert_dir_list:
            Library.objects.bulk_create(insert_dir_list)
            
        for dirname, links in book_dict.items():
            for val in links:
                url, icon_u, add_date, title, descr = val
                logger.info(val)
                add_date = datetime.fromtimestamp(int(add_date))
                lib = Library(usr=usr, directory=dirname, url=url,
                              icon_url=icon_u, timestamp=add_date,
                              title=title, summary=descr)
                insert_links_list.append(lib)
                url_list.append(url)
                
        if insert_links_list:
            Library.objects.bulk_create(insert_links_list)
            
        qlist = Library.objects.filter(usr=usr, url__in=url_list)
        row_list = []
        for row in qlist:
            icon_url = row.icon_url
            row_id = row.id
            url = row.url
            if url:
                row.media_path = cls.get_media_path(url, row_id)
            final_favicon_path = os.path.join(settings.FAVICONS_STATIC, str(row_id) + '.ico')
            row_list.append((row.icon_url, final_favicon_path))
            row.save()
        for iurl, dest in row_list:
            if iurl and iurl.startswith('http'):
                cls.vnt.get(iurl, out=dest)
        
        if (settings_row and (settings_row.auto_archive
                or settings_row.auto_summary or settings_row.autotag)):
            for row in qlist:
                if row.url:
                    dbxs.process_add_url(usr, row.url, row.directory,
                                         archive_html=False, row=row,
                                         settings_row=settings_row,
                                         media_path=row.media_path)
            
            
    @staticmethod
    def get_media_path(url, row_id):
        content_type = guess_type(url)[0]
        if content_type and content_type == 'text/plain':
           ext = '.txt' 
        elif content_type:
            ext = guess_extension(content_type)
        else:
            ext = '.htm'
        out_dir = ext[1:].upper()
        out_title = str(row_id) + str(ext)
        media_dir = os.path.join(settings.ARCHIVE_LOCATION, out_dir)
        if not os.path.exists(media_dir):
            os.makedirs(media_dir)
        
        media_path_parent = os.path.join(media_dir, str(row_id))
        if not os.path.exists(media_path_parent):
            os.makedirs(media_path_parent)
                
        media_path = os.path.join(media_path_parent, out_title)
        return media_path
        
    @staticmethod
    def convert_bookmark_to_dict(import_file, mode='file'):
        links_dict = {}
        if mode == 'file':
            content = ""
            with open(import_file, 'r', encoding='utf-8') as fd:
                content = fd.read()
        else:
            content = import_file
        if content:
            content = re.sub('ICON="(.*?)"', "", content)
            ncontent = re.sub('\n', " ", content)
            links_group = re.findall('<DT><H3(.*?)/DL>', ncontent)
            nsr = 0
            nlinks = []
            for i, j in enumerate(links_group):
                j = j + '<DT>'
                nlinks.clear()
                dirfield = re.search('>(?P<dir>.*?)</H3>', j)
                if dirfield:
                    dirname = html.unescape(dirfield.group('dir'))
                else:
                    dirname = 'Unknown'
                links = re.findall('A HREF="(?P<url>.*?)"(?P<extra>.*?)<DT>', j)
                for url, extra in links:
                    dt = re.search('ADD_DATE="(?P<add_date>.*?)"', extra)
                    add_date = dt.group('add_date')
                    dt = re.search('ICON_URI="(?P<icon>.*?)"', extra)
                    if dt:
                        icon_u = dt.group('icon')
                    else:
                        icon_u = ''
                    dt = re.search('>(?P<title>.*?)</A>', extra)
                    if dt:
                        title = html.unescape(dt.group('title'))
                    else:
                        title = 'No Title'
                    dt = re.search('<DD>(?P<descr>.*?)(<DT>)?', extra)
                    if dt:
                        descr = html.unescape(dt.group('descr'))
                    else:
                        descr = 'Not Available'
                    logger.debug(url)
                    nlinks.append((url, icon_u, add_date, title, descr))
                if dirname in links_dict:
                    dirname = '{}-{}'.format(dirname, nsr)
                    nsr += 1
                links_dict.update({dirname:nlinks.copy()})
        return links_dict
    

