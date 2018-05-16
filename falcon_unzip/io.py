from __future__ import division
from falcon_kit.io import (
        serialize, deserialize, log, mkdirs, syscall, capture, eng,
        rm, touch, filesize, exists_and_not_empty,
        yield_abspath_from_fofn, cd,
)
import commands
import json
import logging
import msgpack
import os
import pprint
import re
import subprocess

try:
    # pylint: disable=no-name-in-module, import-error, fixme, line-too-long
    from pysam.calignmentfile import AlignmentFile#, AlignmentHeader
except ImportError:
    # pylint: disable=no-name-in-module, import-error, fixme, line-too-long
    from pysam.libcalignmentfile import AlignmentFile#, AlignmentHeader

LOG = logging.getLogger(__name__)


def validate_samtools(samtools_output):
    """Given the result of a bare call to 'samtools',
    prove our $PATH is using at least version 1.3.0
    """
    re_Version = re.compile(r'Version: (?P<major>\d+)\.(?P<minor>\d+)\.(?P<subminor>\d+)')
    mo = re_Version.search(samtools_output)
    if not mo:
        msg = samtools_output + '\n---\nCould not discern version of samtools. We need at least 1.3.0. Good luck!'
        LOG.warning(msg)
        return
    major = int(mo.group('major'))
    minor = int(mo.group('minor'))
    if major < 1 or (major == 1 and minor < 3):
        msg = 'samtools is version {}.{}.{}'.format(
                major, minor, mo.group('subminor'))
        msg += ', but we require >= 1.3.0'
        raise Exception(msg)


def validate_config(config):
    # This simple and quick check catches common problems early.
    # This code might go somewhere else someday.
    smrt_bin_cmds = [
        'blasr', 'samtools', 'pbalign', 'variantCaller',
    ]
    path_cmds = [
        'minimap2',
        'nucmer',
        'show-coords',
        'fc_rr_hctg_track2.exe',
    ]
    LOG.info('PATH={}'.format(os.environ['PATH']))
    try:
        capture('which which')
    except Exception:
        LOG.warning('Could not find "which" command. Skipping checks for "blasr", etc.')
        return
    for cmd in smrt_bin_cmds + path_cmds:
        syscall('which ' + cmd)
    syscall('show-coords -h')
    syscall('nucmer --version')
    syscall('minimap2 --version')

    samtools_output = commands.getoutput('samtools')
    validate_samtools(samtools_output)


def yield_bam_fn(input_bam_fofn_fn):
    log('Reading BAM names from FOFN {!r}'.format(input_bam_fofn_fn))
    fofn_basedir = os.path.normpath(os.path.dirname(input_bam_fofn_fn))

    def abs_fn(maybe_rel_fn):
        if os.path.isabs(maybe_rel_fn):
            return maybe_rel_fn
        else:
            return os.path.join(fofn_basedir, maybe_rel_fn)
    for row in open(input_bam_fofn_fn):
        yield abs_fn(row.strip())


def substitute(yourdict):
    """
    >>> list(sorted(substitute({'a': '_{b}_', 'b': 'X'}).items()))
    [('a', '_X_'), ('b', 'X')]
    """
    mydict = dict(yourdict)
    for k, v in yourdict.items():
        if '{' in v:
            mydict[k] = v.format(**mydict)
    return mydict
