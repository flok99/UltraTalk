#! /usr/bin/python3

# This script was written by Folkert van Heusden.
# mail@vanheusden.com

# The license is AGPL v3.0.

import chess
import chess.pgn
import chess.uci
from datetime import date
import os
import platform
import random
import subprocess
import sys
import tempfile
import time

debug = False
uci_program = '/usr/games/stockfish'
#uci_program = '/home/folkert/Projects/QueenBee/tags/v0.9.1_2205/trunk/Embla'
#uci_program = 'shallow-blue/shallowblue'
pgn_file = 'test.pgn'
msx_max_speed = False
msx_color = 'W'
search_time = 1000

vram_bin = tempfile.mktemp()
tcl_script = tempfile.mktemp()

fh = open(tcl_script, 'w')
fh.write('proc dump {} {\n')
fh.write('    save_debuggable VRAM %s 0 16384\n' % (vram_bin + '.tmp'))
fh.write('    file rename -force -- %s %s\n' % (vram_bin + '.tmp', vram_bin))
fh.write('    after realtime 0.5 dump\n')
fh.write('}\n')
fh.write('\n')
fh.write('set power 1\n')
if msx_max_speed:
    fh.write('set throttle off\n')
fh.write('\n')
fh.write('after realtime 0.5 dump\n')
fh.close()

def read_screen():
    while not os.path.exists(vram_bin):
        time.sleep(0.5)

    fh = open(vram_bin, 'rb')
    if fh == None:
        return ' ' * 768

    fh.seek(0x3800)
    data = fh.read(768)

    fh.close()

    return data

def screen_as_array():
    lines = read_screen()
    line_width = 32
    return [lines[i:i+line_width] for i in range(0, len(lines), line_width)]

def send_cmd(proc, cmd):
    if debug:
        print('> %s' % cmd)

    proc.stdin.write(('<command>%s</command>\r\n' % cmd).encode())
    proc.stdin.flush()

    while True:
        reply = str(proc.stdout.readline())
        if debug:
            print('< %s' % reply.replace('\n', ''))

        if 'result="ok"' in reply:
            break

def type_on_kb(proc, text):
    send_cmd(proc, 'type_via_keyboard -release -freq 2 "%s"' % text)

def init(proc, color, tt):
    if debug:
        print('# wait for PAL')

    while True:
        scr = screen_as_array()
        if 'Play Analyse or Load' in str(scr[3]):
            type_on_kb(proc, 'P')
            break
        time.sleep(0.5)

    if debug:
        print('# wait for color')
    while True:
        scr = screen_as_array()
        if 'Your colour (B,W):' in str(scr[4]):
            type_on_kb(proc, color)
            break
        time.sleep(0.5)

    if debug:
        print('# wait for time')
    while True:
        scr = screen_as_array()
        if 'Time Limit (Seconds)' in str(scr[5]):
            t = tt / 1000
            if t < 1:
                t = 1
            type_on_kb(proc, '%d\r' % t)
            break
        time.sleep(0.5)

    if debug:
        print('# initted')

def wait_for_play_screen():
    while True:
        scr = screen_as_array()

        line = str(scr[5])
        if 'PLAYER  MSX' in line or 'MSX   PLAYER' in line:
            return scr

        time.sleep(0.5)

def get_move_nr():
    scr = wait_for_play_screen()

    return int(scr[15][0:2].decode('ascii'))

def convert_move(board, move, color):
    #print(move, color)

    umove = move.upper()

    if 'O-O-O' in umove:
        if color:
            return chess.Move.from_uci('e1c1')

        return chess.Move.from_uci('e8c8')

    if 'O-O' in umove:
        if color:
            return chess.Move.from_uci('e1g1')

        return chess.Move.from_uci('e8g8')

    temp = chess.Move.from_uci(move[0:2] + move[3:5])

    # promotion?
    if board.piece_at(temp.from_square).piece_type == chess.PAWN:
        if move[4] == '8' or move[4] == '1':
            #print(' *** PROMOTION ***')
            return chess.Move.from_uci(move[0:2] + move[3:5] + 'q')

    return temp

def wait_for_black_move(boarboardd):
    while True:
        scr = wait_for_play_screen()

        if debug:
            print(scr[14])
            print(scr[15])
            print(scr[16])

        row14 = scr[14][0:14].decode('ascii')

        end_of_move = row14[13]
        wait_for_next = scr[15][0:14].decode('ascii')[3]

        if debug:
            print(end_of_move, wait_for_next)

        if (end_of_move != ' ' or row14[14:17] == 'O-O' or row14[13:18] == 'O-O-O') and wait_for_next == '#' or 'MATE' in scr[16][0:14].decode('ascii'):
            break

        time.sleep(0.1)

    latest_move = scr[14][9:14].decode('ascii').lower()

    if latest_move == 'check':
        latest_move = scr[13][9:14].decode('ascii').lower()

    return convert_move(board, latest_move, False)

def wait_for_white_move(board):
    while True:
        scr = wait_for_play_screen()

        if debug:
            print(scr[14])
            print(scr[15])
            print(scr[16])

        row15 = scr[15][0:14].decode('ascii')

        end_of_move = row15[7]
        wait_for_next = scr[15][0:14].decode('ascii')[9]

        if debug:
            print(end_of_move, wait_for_next)

        if (end_of_move != ' ' or row15[4:7] == 'O-O' or row15[3:8] == 'O-O-O') and wait_for_next == '#' or 'MATE' in scr[16][0:14].decode('ascii'):
            break

        time.sleep(0.1)

    latest_move = scr[15][3:8].decode('ascii').lower()

    if latest_move == 'check':
        latest_move = scr[14][3:8].decode('ascii').lower()

    return convert_move(board, latest_move, True)

def dump_screen():
    scr = wait_for_play_screen()

    for l in scr:
        print('%s' % l)

def send_move(proc, m, color):
    uci_move = m.uci()
    msx_move = uci_move[0:2] + '-' + uci_move[2:4]

    if debug:
        print('send move %s %d' % (msx_move, color))

    type_on_kb(proc, '%s' % msx_move[0])
    while True:
        scr = wait_for_play_screen()

        if debug:
            print('14 ', scr[14][0:14])
            print('15 ', scr[15][0:14])

        if color:
            line = scr[15][0:14].decode('ascii')
            if line[3] != '#' or line[4] == 'O':
                break
        else:
            line = scr[15][0:14].decode('ascii')
            if line[9] != '#' or line[10] == 'O':
                break

        time.sleep(0.25)

    type_on_kb(proc, '%s\r' % msx_move[1:])
    while True:
        scr = wait_for_play_screen()

        if debug:
            print('14 ', scr[14][0:14])
            print('15 ', scr[15][0:14])

        if color:
            if scr[15][0:14].decode('ascii')[3] == '#':
                break
        else:
            if scr[15][0:14].decode('ascii')[9] == '#':
                break

        msg = scr[15][0:14].decode('ascii')
        if 'MATE' in msg or 'CHECK' in msg or 'MATE' in scr[16][0:14].decode('ascii'):
            break

        time.sleep(0.25)

uc = chess.uci.popen_engine(uci_program)
uc.uci()
print(uc.name)
uc.debug(True)
uc.ucinewgame()

proc = subprocess.Popen(['openmsx', '-machine', 'Philips_NMS_8250', '-diska', 'ultrachess.dsk', '-script', tcl_script, '-control', 'stdio'], stdout=subprocess.PIPE, stdin=subprocess.PIPE)

proc.stdin.write('<openmsx-control>\r\n'.encode())

board = chess.Board()

color = False
if msx_color == 'W':
    color = True
    init(proc, 'B', search_time)
else:
    init(proc, 'W', search_time)

game = chess.pgn.Game()
game.headers['Event'] = 'UltraChess on OpenMSX versus %s on %s' % (uc.name, platform.machine())
if msx_color == 'W':
    game.headers['White'] = 'UltraChess'
    game.headers['Black'] = uc.name
else:
    game.headers['White'] = uc.name
    game.headers['Black'] = 'UltraChess'
d = date.today()
game.headers['Site'] = platform.node()
game.headers['Date'] = '%04d.%02d.%02d' % (d.year, d.month, d.day)

node = None

while True:
    if board.is_game_over():
        break

    if board.turn:
        print('%d] ' % board.fullmove_number, end='', flush=True)

    s = time.time()
    if board.turn != color:
        uc.isready()
        uc.position(board)
        (move, ponder_move) = uc.go(movetime = search_time)

        send_move(proc, move, board.turn)
        board.push(move)

        print('%s ' % move, end='', flush=True)

    else:
        if board.turn:
           move = wait_for_white_move(board)
        else:
           move = wait_for_black_move(board)

        board.push(move)

        print('%s ' % move, end='', flush=True)

    if node == None:
        node = game.add_variation(move)
    else:
        node = node.add_variation(move)

    if debug:
        print('%f ' % (time.time() - s), end='', flush=True)

    if board.turn:
        print('')

try:
    game.headers['Result'] = board.result()

    print(game, file=open(pgn_file, 'a'), end="\n\n")
except Exception as e:
    print(game, stdout, end="\n\n")

proc.stdin.write('</openmsx-control>\r\n'.encode())

proc.kill()

os.unlink(tcl_script)
os.unlink(vram_bin)

sys.exit(0)
