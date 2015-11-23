import sys, logging

try: 
  from app import voip, sipstackcaller
  from std import rfc3261, rfc2396, rfc3550, rfc4566, kutil
  from external import log
except ImportError: print 'Please install p2p-sip and include p2p-sip/src and p2p-sip/src/external in your PYTHONPATH'; traceback.print_exc(); sys.exit(1)

logger = logging.getLogger('answermachine')

class Options(object):
  def __init__(self, user, domain, password, bac=None, int_ip='0.0.0.0', port=0, register=True, register_interval=3600, retry_interval=60, auto_respond=200, auto_respond_after=3, auto_terminate_after=0, transports='udp', listen_queue=5, max_size=4096, fix_nat=False, user_agent=None, strict_route=False, uri=None, proxy='', send='', listen=True):
    self.user, self.domain, self.password, self.bac, self.int_ip, self.port, self.proxy = user, domain, password, bac, int_ip, port, proxy 
    self.register, self.register_interval, self.retry_interval, self.auto_respond, self.auto_respond_after, self.auto_terminate_after = register, register_interval, retry_interval, auto_respond, auto_respond_after, auto_terminate_after
    self.transports, self.listen_queue, self.max_size, self.fix_nat, self.user_agent, self.strict_route, self.uri = transports, listen_queue, max_size, fix_nat, user_agent, strict_route, uri
    self.send, self.listen = send, listen
    self.streams_loopback, self.audio = False, False

class Answerer(sipstackcaller.Caller):
  def __init__(self, options):
    sipstackcaller.Caller.__init__(self, options)

  def receivedInvite(self, ua, request):
    logger.info('received INVITE')
    if self.options.auto_respond >= 200 and self.options.auto_respond < 300:
      call = Call(self, ua.stack)
      call.receivedRequest(ua, request)
    elif self.options.auto_respond:
      ua.sendResponse(ua.createResponse(self.options.auto_respond, 'Decline'))
    
class Call(sipstackcaller.Call):
  def __init__(self, app, stack):
    sipstackcaller.UA.__init__(self, app, stack)
    self.media, self.audio, self.state = None, None, 'idle'
    audio = rfc4566.SDP.media(media='audio')
    audio.fmt = []
    audio.fmt.append( rfc4566.attrs(pt=0, name='pcmu', rate=8000, params="1") )
    audio.fmt.append( rfc4566.attrs(pt=8, name='pcma', rate=8000, params="1") )
    audio.fmt.append( rfc4566.attrs(pt=3, name='gsm', rate=8000, params="1") )
    audio.fmt.append( rfc4566.attrs(pt=9, name='g722', rate=16000, params="1") )
    audio.fmt.append( rfc4566.attrs(pt=101, name='telephone-event', rate=8000, fmt_params="0-11") )
    audio.direction = 'sendonly'
    video = rfc4566.SDP.media(media='video')
    video.fmt = []
    video.fmt.append( rfc4566.attrs(pt=34, name='H263', rate=90000) )
    video.fmt.append( rfc4566.attrs(pt=98, name='H263-1998', rate=90000, fmt_params="CIF=1;QCIF=1") )
    video.fmt.append( rfc4566.attrs(pt=99, name='MP4V-ES', rate=90000, fmt_params="profile-level-id=3") )
    video.fmt.append( rfc4566.attrs(pt=102, name='H264', rate=90000) )
    video.fmt.append( rfc4566.attrs(pt=103, name='VP8', rate=90000) )
    video.fmt.append( rfc4566.attrs(pt=104, name='H264', rate=90000,fmt_params="packetization-mode=1"))
    self._audio_and_video_streams, self._queue = [audio, video], []
        
if __name__ == '__main__': 
  try:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter('%(asctime)s|%(module)s|%(lineno)s|%(levelname)s|%(message)s', datefmt='%H:%M:%S'))
    logging.getLogger().addHandler(handler)

    argv = sys.argv
    i, username, password, media, bac = 1, None, None, None, None
    int_ip = '0.0.0.0' 
    while i < len(argv):
      if argv[i] == '-u':
        if username:		
          username, password, media = None, None, None		
        username = argv[i+1]
      elif argv[i] == '-p':
        password = argv[i+1]
      elif argv[i] == '-m':
        media = argv[i+1]
      elif argv[i] == '-b':
        bac = argv[i+1]
      elif argv[i] == '-i':
        int_ip = argv[i+1]
      i += 2		

    (user, domain) = username.split('@')
    options = Options(user, domain, password, bac=bac, int_ip=int_ip)

    answerer = Answerer(options)
    answerer.wait()
  except KeyboardInterrupt:
    print '' # to print a new line after ^C
  except: 
    logger.exception('exception')
    sys.exit(-1)
  try:
    answerer.close()
  except KeyboardInterrupt:
    print ''

