import gevent, sys
from gevent import monkey; monkey.patch_all()
from gevent.pywsgi import WSGIServer
from cgi import parse_qs, escape
import logging
from logging import config
logging.config.fileConfig('logging.conf')
#logger = logging.getLogger(__name__)
logger = logging.getLogger()

from caller import Options
from gevent import queue

freeAccounts = queue.Queue()

from app import sipstackcaller

bac, int_ip = None, None
maxwait = 5

import Queue

def application(env, start_response):
  d = parse_qs(env['QUERY_STRING'])
  peer = d.get('peer', ['unknown'])[0]
  peer = escape(peer)
  peer = 'sip:'+peer+'@gd.ctcims.cn'
  logger.info('calling ' + peer)

  response_body = ''

  if env['REMOTE_ADDR'].startswith('192.168') or env['REMOTE_ADDR'] == '127.0.0.1':
    try:
      (user, domain, password) = freeAccounts.get(timeout=maxwait)
      options = Options(user, domain, password, bac=bac, int_ip=int_ip, to=peer, uri=peer)
      caller = sipstackcaller.Caller(options)
      gevent.spawn_later(30, hangup, caller, (user, domain, password))
      status = '200 OK'
    except Queue.Empty:
      logger.warn('get from queue  timeout')
      status = '503 Service Unavailable' 
  else:
    status = '403 Forbidden'

  response_headers = [
        ('Content-Type', 'text/plain'),
        ('Content-Length', str(len(response_body)))
  ]
  start_response(status, response_headers)

  return [response_body]  

def hangup(caller, account):
  caller.close()
  freeAccounts.put(account)
  logger.info('hangup call to ' + str(caller.options.to))

if __name__ == '__main__':
  try:
    argv = sys.argv
    i, username, password, media, bac = 1, None, None, None, None
    int_ip = '0.0.0.0' 
    jobs, callers = [], []
    while i < len(argv):
      if argv[i] == '-u':
        if username:		
          (user, domain) = username.split('@')
          freeAccounts.put((user, domain, password))
          username, password = None, None		
        username = argv[i+1]
      elif argv[i] == '-p':
        password = argv[i+1]
      elif argv[i] == '-b':
        bac = argv[i+1]
      elif argv[i] == '-i':
        int_ip = argv[i+1]
      i += 2		
    (user, domain) = username.split('@')
    freeAccounts.put((user, domain, password))
  except:
    logger.exception('exception')
    sys.exit(-1)
    
  print('Serving on 8088...')
  WSGIServer(('', 8088), application, log=logger).serve_forever()
