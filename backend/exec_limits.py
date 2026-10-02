"""Trusted child launcher: set limits after exec, never run Python preexec_fn in a threaded server."""
import os
import resource
import sys

resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024**2, 64 * 1024**2))
resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
os.execv(sys.argv[1], sys.argv[1:])
