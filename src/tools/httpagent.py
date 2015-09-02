import BaseHTTPServer
import subprocess

cmds = ['netstat']

class ShellRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
  def do_GET(self):
    nothing, cmd, args = self.path.split('/')
    if cmd in cmds:	
      s = subprocess.call([cmd], stdout=self.wfile)
    else:
      self.send_error(405)	

def test(HandlerClass = ShellRequestHandler,
         ServerClass = BaseHTTPServer.HTTPServer):
    BaseHTTPServer.test(HandlerClass, ServerClass)

if __name__ == '__main__':
    test()	