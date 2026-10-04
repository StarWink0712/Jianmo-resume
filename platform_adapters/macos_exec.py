"""Trusted child launcher. Never execute native limits in a threaded preexec_fn."""

import os
import sys


def main():
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024**2, 64 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    os.execv(sys.argv[1], sys.argv[1:])


if __name__ == '__main__':
    main()
