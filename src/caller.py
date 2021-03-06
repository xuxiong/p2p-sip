import sys, logging, gevent,traceback

try: 
  from app import voip, sipstackcaller
  from std import rfc3261, rfc2396, rfc3550, rfc4566, kutil
except ImportError: print 'Please install p2p-sip and include p2p-sip/src and p2p-sip/src/external in your PYTHONPATH'; traceback.print_exc(); sys.exit(1)

from logging import config
logging.config.fileConfig('logging.conf')
logger = logging.getLogger(__name__)

try:
    from subprocess import DEVNULL # py3k
except ImportError:
    import os
    DEVNULL = open(os.devnull, 'wb')

class Options(object):
  def __init__(self, user, domain, password, bac=None, int_ip='0.0.0.0', port=0, register=True, register_interval=3600, retry_interval=60, auto_respond=200, auto_respond_after=3, auto_terminate_after=0, transports='udp', listen_queue=5, max_size=4096, fix_nat=False, user_agent=None, strict_route=False, uri=None, proxy='', send='', listen=False, mediafile=None, vfile=None, afile=None, to=None, subject=None):
    self.user, self.domain, self.password, self.bac, self.int_ip, self.port, self.proxy = user, domain, password, bac, int_ip, port, proxy 
    self.register, self.register_interval, self.retry_interval, self.auto_respond, self.auto_respond_after, self.auto_terminate_after = register, register_interval, retry_interval, auto_respond, auto_respond_after, auto_terminate_after
    self.transports, self.listen_queue, self.max_size, self.fix_nat, self.user_agent, self.strict_route, self.uri = transports, listen_queue, max_size, fix_nat, user_agent, strict_route, uri
    self.send, self.listen = send, listen
    self.streams_loopback, self.audio = False, True 
    self.mediafile, self.vfile, self.afile = mediafile, vfile, afile
    self.video_capture_capability = False
    self.video_display_capability = False
    self.has_sdp = True
    self.subject = subject
    self.to = rfc2396.Address(to)
    self.uri = rfc2396.URI(uri)

class Answerer(sipstackcaller.Caller):
  def __init__(self, options):
    sipstackcaller.Caller.__init__(self, options)

  def receivedInvite(self, ua, request):
    logger.info('received INVITE')
    if self.options.auto_respond >= 200 and self.options.auto_respond < 300:
      call = Call(self, ua.stack, self.options.mediafile, self.options.vfile, self.options.afile)
      call.receivedRequest(ua, request)
    elif self.options.auto_respond:
      ua.sendResponse(ua.createResponse(self.options.auto_respond, 'Decline'))
    
  def receivedNotify(self, ua, request):
    logger.info('received: %s', request.body)
    ua.sendResponse(ua.createResponse(200, 'OK'))
            
from gevent import subprocess

class Call(sipstackcaller.Call):
  def __init__(self, app, stack, mediafile, vfile, afile):
    sipstackcaller.UA.__init__(self, app, stack)
    self.mediafile, self.vfile, self.afile = mediafile, vfile, afile
    self.media, self.audio, self.state = None, None, 'idle'
    audio = rfc4566.SDP.media(media='audio')
    audio.fmt = []
    audio.fmt.append( rfc4566.attrs(pt=8, name='pcma', rate=8000, params="1") )
    audio.fmt.append( rfc4566.attrs(pt=3, name='gsm', rate=8000, params="1") )
    audio.fmt.append( rfc4566.attrs(pt=9, name='g722', rate=16000, params="1") )
    audio.fmt.append( rfc4566.attrs(pt=101, name='telephone-event', rate=8000, fmt_params="0-11") )
    audio.direction = 'sendonly'
    video = rfc4566.SDP.media(media='video')
    video.fmt = []
    video.fmt.append( rfc4566.attrs(pt=104, name='H264', rate=90000,fmt_params="packetization-mode=1"))
    video.direction = 'sendonly'
    self._audio_and_video_streams, self._queue = [audio, video], []
    self.p = None
        
  def startStreams(self):
    logger.debug('starting streaming')
    yoursdp = self.media.yoursdp
    logger.info('VideoREMOTE=%s:%d', yoursdp['c'].address, [m for m in yoursdp['m'] if m.media=='video'][0].port) 
    vhost, vport = yoursdp['c'].address, [m for m in yoursdp['m'] if m.media=='video'][0].port
    logger.info('AudioREMOTE=%s:%d', yoursdp['c'].address, [m for m in yoursdp['m'] if m.media=='audio'][0].port) 
    ahost, aport = yoursdp['c'].address, [m for m in yoursdp['m'] if m.media=='audio'][0].port
    #cmd = ['ffmpeg', '-i', self.mediafile, '-vcodec', 'h264', '-an', '-b:v', '640k', '-pix_fmt', 'yuv420p', '-payload_type', '122', '-s', '320*240', '-r', '20', '-profile:v', 'baseline', '-level', '1.2', '-f', 'rtp', 'rtp://' + vhost + ':' + str(vport)]
    if self.vfile and self.afile:
      cmd = ['ffmpeg', '-re', '-i', self.vfile, '-vcodec', 'copy', '-an', '-b:v',  '128k', '-pix_fmt', 'yuv420p', '-payload_type', '122', '-s', '320*240', '-r', '20', '-level', '1.3', '-f', 'rtp', 'rtp://' + vhost + ':' + str(vport), '-i', self.afile, '-vn', '-acodec', 'copy', '-ar', '16k', '-ab', '1', '-vbr', 'on', '-payload_type', '109', '-f', 'rtp', 'rtp://' + ahost + ':' + str(aport) ]
    else:
      cmd = ['ffmpeg', '-re', '-i', self.mediafile, '-vcodec', 'h264', '-an', '-b:v', '768k', '-pix_fmt', 'yuv420p', '-payload_type', '122', '-s', '320*240', '-r', '20', '-profile:v', 'baseline', '-level', '1.3', '-f', 'rtp', 'rtp://' + vhost + ':' + str(vport), '-vn', '-acodec', 'libopus', '-ar', '16k', '-ab', '32k', '-ac', '1', '-vbr', 'on', '-payload_type', '109', '-f', 'rtp', 'rtp://' + ahost + ':' + str(aport)]
    logger.info(' '.join(cmd))
    self.p = gevent.subprocess.Popen(cmd, stdout=DEVNULL, stderr=DEVNULL)
    self.p.rawlink(self._bye)

  def _bye(self, p):
    code = p.poll()
    logger.debug('ffmpeg exit %d', code) 
    if code == 0:
      logger.debug('goodbye to peer')
      self._autoTerminate()
    
  def stopStreams(self):
    logger.debug("stopping streaming")
    if self.p and self.p.poll()==None:
      self.p.kill()
      self.p = None
    
if __name__ == '__main__': 
  def addjob(jobs, answerers, username, password, bac, int_ip, mediafile, vfile, afile, to):
    (user, domain) = username.split('@')
    options = Options(user, domain, password, register_interval=1800, bac=bac, int_ip=int_ip, mediafile=mediafile, vfile=vfile, afile=afile, to=to, uri=to)
    answerer = Answerer(options)
    jobs.append(gevent.spawn(answerer.wait))
    answerers.append(answerer)

  try:
    argv = sys.argv
    i, username, password, media, bac, to = 1, None, None, None, None, None
    vfile, afile = None, None
    int_ip = '0.0.0.0' 
    jobs, answerers = [], []
    while i < len(argv):
      if argv[i] == '-u':
        if username:		
          addjob(jobs, answerers, username, password, bac, int_ip, media, vfile, afile)
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
      elif argv[i] == '-v':
        vfile = argv[i+1]
      elif argv[i] == '-a':
        afile = argv[i+1]
      elif argv[i] == '-t':
        to = argv[i+1]
      i += 2		

    addjob(jobs, answerers, username, password, bac, int_ip, media, vfile, afile, to)
    gevent.joinall(jobs)
  
  except KeyboardInterrupt:
    print '' # to print a new line after ^C
  except: 
    logger.exception('exception')
    sys.exit(-1)
  
  try:
    jobs = [gevent.spawn(x.close) for x in answerers]
    gevent.joinall(jobs, timeout=5)
  except KeyboardInterrupt:
    print ''
  
