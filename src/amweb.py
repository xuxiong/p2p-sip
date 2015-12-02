import gevent, sys
from gevent import monkey; monkey.patch_all()
from gevent.pywsgi import WSGIServer
from cgi import parse_qs, escape
import logging
from logging import config
logging.config.fileConfig('logging.conf')
logger = logging.getLogger(__name__)

import answermachine
from gevent import queue

'''
tasks = Queue()
class AnswerWorker(answermachine.Answerer):
  def __init__(self, options):
    answermachine.Answerer.__init__(self, options)
    self._call = None

  def receivedInvite(self, ua, request):
    logger.info('received INVITE')
    self._call.receivedRequest(ua, request)

  def wait(self):
    while True:
      task = tasks.get()
      if task == None:
        break 
      else:
        (self._call, result) = task
        self._call.app, self._call._stack = self, self.stack
        result.set(self.options.user)
'''
freeAccounts = queue.Queue()

from app import sipstackcaller

class Answerer(answermachine.Answerer):
  def __init__(self, options):
    self.options, self._ua, self._closeQueue, self.stacks = options, [], queue.Queue(), sipstackcaller.Stacks(self, options)
    self.stacks.start()
    self._ua.append(Register(self, self.stacks.default))

  def receivedInvite(self, ua, request):
    logger.info('received INVITE')
    if self.options.auto_respond >= 200 and self.options.auto_respond < 300:
      call = Call(self, ua.stack, self.options.mediafile, self.options.vfile, self.options.afile)
      call.receivedRequest(ua, request)
    elif self.options.auto_respond:
      ua.sendResponse(ua.createResponse(self.options.auto_respond, 'Decline'))
 
class Register(sipstackcaller.Register):
  def _scheduleRefresh(self, response, handler):pass
  def _scheduleRetry(self, handler):pass

class Call(answermachine.Call):
  def __init__(self, app, stack, mediafile, vfile, afile):
    answermachine.Call.__init__(self, app, stack, mediafile, vfile, afile)
    self._app = app

  def stopStreams(self):
#    answermachine.Call.stopStreams(self)
    logger.debug("stopping streaming")
    if self.p and self.p.poll()==None:
      self.p.kill()
      self.p = None
    gevent.spawn(self._app.close)
    freeAccounts.put((self.options.user, self.options.domain, self.options.password))

files = {'0':('/tmp/iPhone6_ad2.mp4', '/tmp/iPhone6_ad2.264', '/tmp/iPhone6_ad2.opus'), }
bac, int_ip = None, None
maxwait = 5

import Queue

def application(env, start_response):
  d = parse_qs(env['QUERY_STRING'])
  type = d.get('type', ['0'])[0]
  type = escape(type)
  peer = d.get('peer', ['unknown'])[0]
  peer = escape(peer)

  response_body = ''
  if type in files:
    try:
      (user, domain, password) = freeAccounts.get(timeout=maxwait)
      response_body = user
      options = answermachine.Options(user, domain, password, bac=bac, int_ip=int_ip, mediafile=files[type][0], vfile=files[type][1], afile=files[type][2])
      answerer = Answerer(options)
      gevent.spawn(answerer.wait)
      status = '200 OK'
    except Queue.Empty:
      status = '503 Service Unavailable' 
  else:
    status = '400 Bad Request'

  response_headers = [
        ('Content-Type', 'text/plain'),
        ('Content-Length', str(len(response_body)))
  ]
  start_response(status, response_headers)

  return [response_body]  

if __name__ == '__main__':
  try:
    argv = sys.argv
    i, username, password, media, bac = 1, None, None, None, None
    vfile, afile = None, None
    int_ip = '0.0.0.0' 
    jobs, answerers = [], []
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
