# -*- coding: utf-8 -*-
#Copyright (c) 2011 Walter Bender

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

import gtk
import os
import codecs

from gettext import gettext as _

from random import randrange

from utils.gplay import play_audio_from_file

import logging
_logger = logging.getLogger('infused-activity')

try:
    from sugar.graphics import style
    GRID_CELL_SIZE = style.GRID_CELL_SIZE
except ImportError:
    GRID_CELL_SIZE = 0

from genpieces import generate_card
from utils.sprites import Sprites, Sprite

# TRANS: e.g., This yellow sign is said u like up.
MSGS = [_('This {0} sign is said {1} like {2}').format('%s', '%s', '%s\n\n') + \
        _('Reading from left to right, read the sounds one at a time. You \
can use your finger to follow along.'),
        _('This {0} sign is said {1} like {2}').format('%s', '%s', '%s'),
        _('This {0} sign is lightly said {1} like {2}').format('%s', '%s',
                                                               '%s'),
        _('This {0} sign is said together with other sounds as in: {1}').format(
        '%s', '%s'),
        _('This {0} sign is said together with other sounds as in: {1}').format(
        '%s', '%s'),
        _('When it looks like this \n we read it the same way.')]
FIRST_CARD = 0
VOWEL = 1
LIGHT = 2
CONSONANT = 3
DOUBLE = 4
SECOND_CARD = 5

# Rendering-related constants
KERN = {'i': 0.5, 'I': 0.7, 'l': 0.6, 't': 0.7, 'T': 1.0, 'r': 0.7, 'm': 1.4,
        'w': 1.3, "'": 0.4, 'M': 1.6, 'f': 0.7, 'W': 1.6, 'L': 0.9, 'j': 0.6,
        'J': 0.8, 'c': 0.9, 'z': 0.9, 's': 0.8, 'U': 1.1, ' ':0.7, '.':0.5,
        'y':0.8}
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz:.,' " + \
    u'!Ññáéíóú'


class Page():
    ''' Pages from Infuse Reading method '''

    def __init__(self, canvas, path, level, parent=None):
        ''' The general stuff we need to track '''
        self._activity = parent
        print ALPHABET

        # Starting from command line
        if self._activity is None:
            self._sugar = False
            self._canvas = canvas
        else:
            self._sugar = True
            self._canvas = canvas
            self._activity.show_all()

        self._canvas.set_flags(gtk.CAN_FOCUS)
        self._canvas.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self._canvas.add_events(gtk.gdk.BUTTON_RELEASE_MASK)
        self._canvas.connect("expose-event", self._expose_cb)
        self._canvas.connect("button-press-event", self._button_press_cb)
        self._canvas.connect("button-release-event", self._button_release_cb)
        self._canvas.connect("key_press_event", self._keypress_cb)
        self._width = gtk.gdk.screen_width()
        self._height = gtk.gdk.screen_height()
        self._scale = self._width / 240.
        self._sprites = Sprites(self._canvas)
        self.page = 0
        self._cards = []
        self._double_cards = []
        self._letters = []
        self._colored_letters = []
        self._picture = None
        self._press = None
        self._release = None
        self.gplay = None
        self._final_x = 0
        self._lead = int(self._scale * 15)
        self._margin = int(self._scale * 3)
        self._left = self._margin  # int((self._width - self._scale * 60) / 2.)
        self._x_pos = self._margin
        self._y_pos = self._lead
        self._offset = int(self._scale * 9)  # self._width / 30.)
        self._looking_at_word_list = False

        self._my_canvas = Sprite(self._sprites, 0, 0,
                                gtk.gdk.Pixmap(self._canvas.window,
                                               self._width,
                                               self._height * 2, -1))
        self._my_canvas.set_layer(0)
        self._my_gc = self._my_canvas.images[0].new_gc()
        self._my_gc.set_foreground(
            self._my_gc.get_colormap().alloc_color('#FFFFFF'))

        for c in ALPHABET:
            self._letters.append(Sprite(self._sprites, 0, 0,
                svg_str_to_pixbuf(generate_card(string=c,
                                                colors=['#000000', '#000000'],
                                                font_size=12 * self._scale,
                                                background=False))))

        self.load_level(os.path.join(path, level + '.csv'))
        self.new_page()

    def page_list(self):
        ''' Index into all the cards in the form of a list of phrases '''
        # Already here? Then jump back to current page.
        if self._looking_at_word_list:
            self.new_page()
            return

        save_page = self.page
        self._clear_all()

        rect = gtk.gdk.Rectangle(0, 0, self._width, self._height * 2)
        self._my_canvas.images[0].draw_rectangle(self._my_gc, True, *rect)
        self.invalt(0, 0, self._width, self._height)
        self._my_canvas.set_layer(1)

        self._x_pos, self._y_pos = self._margin, 0

        for i, phrase in enumerate(self.get_phrase_list()):
            if i < len(self._colored_letters):
                self.page = i
                self._render_phrase(phrase, self._my_canvas, self._my_gc)
            else:
                self._render_phrase(phrase.lower(), self._my_canvas,
                                    self._my_gc)
            self._x_pos = self._margin
            self._y_pos += self._lead

        self.page = save_page
        self._looking_at_word_list = True

    def get_phrase_list(self):
        phrase_list = []
        # Each list is a collection of phrases, separated by spaces
        for i, card in enumerate(self._card_data):
            if card[0] == '':
                break
            if card[0] in 'AEIOUY':
                connector = ' ' + _('like') + ' '
            else:
                connector = ' ' + _('as in') + ' '
            phrase_list.append(card[0] + connector + card[1])
        return phrase_list

    def new_page(self):
        ''' Load a new page: a card and a message '''
        if self.page == len(self._word_data):
            self.page = 0
        if self._sugar:
            if self.page < len(self._card_data):
                if hasattr(self._activity, 'sounds_combo'):
                    self._activity.sounds_combo.set_active(self.page)
        if self.page == len(self._cards) and \
           self.page < len(self._card_data):
            # Two-tone cards add some complexity.
            if type(self._color_data[self.page][0]) == type([]):
                top = svg_str_to_pixbuf(generate_card(
                        string=self._card_data[self.page][0].lower(),
                        colors=[self._color_data[self.page][0][0], '#000000'],
                        scale=self._scale,
                        center=True))
                bot = svg_str_to_pixbuf(generate_card(
                        string=self._card_data[self.page][0].lower(),
                        colors=[self._color_data[self.page][0][1], '#000000'],
                        scale=self._scale,
                        center=True))
                # Where to draw the line
                h1 = 9 / 16.
                h2 = 1.0 - h1
                bot.composite(top, 0, int(h1 * top.get_height()),
                              top.get_width(), int(h2 * top.get_height()),
                              0, 0, 1, 1, gtk.gdk.INTERP_NEAREST, 255)
                self._cards.append(Sprite(self._sprites, self._left,
                                          GRID_CELL_SIZE, top))
                stroke = self._test_for_stroke()
                top = svg_str_to_pixbuf(generate_card(
                                string=self._card_data[self.page][0][0].lower(),
                                colors=[self._color_data[self.page][0][0],
                                        '#000000'],
                                font_size=12 * self._scale,
                                background=False, stroke=stroke))
                bot = svg_str_to_pixbuf(generate_card(
                                string=self._card_data[self.page][0][0].lower(),
                                colors=[self._color_data[self.page][0][1],
                                        '#000000'],
                                font_size=12 * self._scale,
                                background=False, stroke=stroke))
                bot.composite(top, 0, int(h1 * top.get_height()),
                              top.get_width(), int(h2 * top.get_height()),
                              0, 0, 1, 1, gtk.gdk.INTERP_NEAREST, 255)
                self._colored_letters.append(Sprite(self._sprites, 0, 0, top))
            else:
                self._cards.append(Sprite(self._sprites, self._left,
                                          GRID_CELL_SIZE,
                                          svg_str_to_pixbuf(generate_card(
                                string=self._card_data[self.page][0].lower(),
                                colors=[self._color_data[self.page][0],
                                        '#000000'],
                                scale=self._scale, center=True))))
                self._double_cards.append(Sprite(self._sprites, self._left,
                                                 self._height + \
                                                     GRID_CELL_SIZE * 2,
                                             svg_str_to_pixbuf(generate_card(
                                string=self._card_data[self.page][0].lower()
                                + self._card_data[self.page][0].lower(),
                                colors=[self._color_data[self.page][0],
                                        '#000000'],
                                scale=self._scale, font_size=40, center=True))))
                stroke = self._test_for_stroke()
                self._colored_letters.append(Sprite(
                        self._sprites, 0, 0, svg_str_to_pixbuf(generate_card(
                                string=self._card_data[self.page][0].lower(),
                                colors=[self._color_data[self.page][0],
                                        '#000000'],
                                font_size=12 * self._scale,
                                background=False, stroke=stroke))))

        self._hide_cards()
        if self.page >= len(self._card_data):
            self.read()
        else:
            self._load_card()
        self._looking_at_word_list = False

    def _test_for_stroke(self):
        ''' Light colors get a surrounding stroke '''
        # TODO: better value test
        if self._color_data[self.page][0][0:4] == '#FFF':
            return True
        else:
            return False

    def _load_card(self):
        ''' a card is a sprite and a message. '''

        vadj = self._activity.scrolled_window.get_vadjustment()
        vadj.set_value(0)
        self._activity.scrolled_window.set_vadjustment(vadj)

        self._cards[self.page].set_layer(2)

        self._x_pos = self._margin
        self._y_pos = self._cards[self.page].rect.y + \
                      self._cards[self.page].images[0].get_height() + self._lead
        rect = gtk.gdk.Rectangle(0, 0, self._width, int(self._height * 2))
        self._my_canvas.images[0].draw_rectangle(self._my_gc, True, *rect)
        self.invalt(0, 0, self._width, int(self._height * 2))

        if self._msg_data[self.page] == CONSONANT:
            text = MSGS[CONSONANT] % (self._color_data[self.page][1],
                                      self._card_data[self.page][1])
        elif self._msg_data[self.page] == DOUBLE:
            text = MSGS[DOUBLE] % (self._color_data[self.page][1],
                                   self._card_data[self.page][1])
        elif self._msg_data[self.page] == LIGHT:
            text = MSGS[LIGHT] % (self._color_data[self.page][1],
                                  self._card_data[self.page][0],
                                  self._card_data[self.page][1])
        else:
            text = MSGS[self._msg_data[self.page]] % (
                self._color_data[self.page][1],
                self._card_data[self.page][0],
                self._card_data[self.page][1])

        for phrase in text.split('\n'):
            self._render_phrase(phrase, self._my_canvas, self._my_gc)
            self._x_pos = self._margin
            self._y_pos += self._lead

        if self._msg_data[self.page] == DOUBLE:
            self._y_pos += self._lead
            self._render_phrase(MSGS[SECOND_CARD].split('\n')[0],
                                self._my_canvas, self._my_gc)
            self._x_pos = self._margin
            self._y_pos += self._lead * 2
            self._double_cards[self.page].move((self._left, self._y_pos))
            self._double_cards[self.page].set_layer(2)
            self._x_pos = self._margin
            self._y_pos = self._double_cards[self.page].rect.y + \
                self._double_cards[self.page].images[0].get_height() + \
                self._lead
            self._render_phrase(MSGS[SECOND_CARD].split('\n')[1],
                                self._my_canvas, self._my_gc)

        # Is there a picture for this page?
        if os.path.exists(os.path.join(os.path.abspath('.'), 'images',
            self._card_data[self.page][1].lower() + '.png')):
            pixbuf = image_file_to_pixbuf(os.path.join(os.path.abspath('.'),
                'images', self._card_data[self.page][1].lower() + '.png'),
                self._scale / 4)
            if self._picture is None:
                self._picture = Sprite(self._sprites,
                                  int(self._width - 320 * self._scale / 2.5),
                                       GRID_CELL_SIZE, pixbuf)
            else:
                self._picture.images[0] = pixbuf
            self._picture.set_layer(2)
        elif self._picture is not None:
            self._picture.set_layer(0)

        # Hide all the letter sprites.
        for l in self._letters:
            l.set_layer(0)
        for l in self._colored_letters:
            l.set_layer(0)
        self._my_canvas.set_layer(0)

    def reload(self):
        ''' Switch back and forth between reading and displaying a card. '''
        if self.page < len(self._card_data):
            self._load_card()
        else:
            self.read()
        if self._sugar:
            self._activity.status.set_label('')

    def read(self):
        ''' Read a word list '''
        self._clear_all()

        rect = gtk.gdk.Rectangle(0, 0, self._width, self._height * 2)
        self._my_canvas.images[0].draw_rectangle(self._my_gc, True, *rect)
        self.invalt(0, 0, self._width, self._height)
        self._my_canvas.set_layer(1)

        my_list = self._word_data[self.page].split('/')

        self._x_pos, self._y_pos = self._margin, self._lead

        for phrase in my_list:
            self._render_phrase(phrase, self._my_canvas, self._my_gc)

            # Put a longer space between each phrase
            self._x_pos += self._offset
            if self._x_pos > self._width * 7 / 8.0:
                self._x_pos, self._y_pos = self._increment_xy(self._y_pos)

        self._looking_at_word_list = False

    def test(self):
        ''' Generate a randomly ordered list of phrases. '''
        self._clear_all()

        rect = gtk.gdk.Rectangle(0, 0, self._width, self._height * 2)
        self._my_canvas.images[0].draw_rectangle(self._my_gc, True, *rect)
        self.invalt(0, 0, self._width, self._height)
        self._my_canvas.set_layer(1)

        phrase_list = self._test_data.split('/')
        list_length = len(phrase_list)

        for i in range(list_length):  # Randomize the phrase order.
            j = randrange(list_length - i)
            tmp = phrase_list[i]
            phrase_list[i] = phrase_list[list_length - 1 - j]
            phrase_list[list_length - 1 - j] = tmp

        self._x_pos, self._y_pos = self._margin, self._lead

        for phrase in phrase_list:
            self._render_phrase(phrase, self._my_canvas, self._my_gc)
            self._x_pos, self._y_pos = self._increment_xy(self._y_pos)
            if self._y_pos > self._height * 2 - self._lead:
                break

        self._looking_at_word_list = False

    def _render_phrase(self, phrase, canvas, gc):
        ''' Draw an individual phase onto the canvas. '''

        # Either we are rendering complete lines or phrases
        lines = phrase.split('\\')
        if len(lines) == 1:  # split a phrase into words
            words = phrase.split()
            for word in words:
                # Will line run off the right edge?
                if self._x_pos + len(word) * self._offset > \
                        self._width - self._margin:
                    self._x_pos, self._y_pos = self._increment_xy(self._y_pos)
                self._draw_a_word(word, canvas, gc)

        else:  # render each line as a unit
            for line in lines:
                self._draw_a_word(line, canvas, gc)
                self._x_pos, self._y_pos = self._increment_xy(self._y_pos)

    def _letter_match(self, word, char, n):
        ''' Does the current position in the word match the letters on
        the card for the current page? '''
        if not self.page < len(self._card_data):
            return False
        if n == 1 and word[char] == self._card_data[self.page][0][0]:
            return True
        if len(word) - char < n:
            return False
        if word[char:char+n] == self._card_data[self.page][0]:
            return True
        return False

    def _draw_a_word(self, word, canvas, gc):
        ''' Process each character in the word '''

        # some colored text is multiple characters
        n = len(self._card_data[self.page][0])

        skip_count = 0
        for char in range(len(word)):
            if skip_count > 0:
                skip_count -= 1
            elif self._letter_match(word, char, n):
                self._draw_pixbuf(
                    self._colored_letters[self.page].images[0],
                    self._x_pos, self._y_pos, canvas, gc)
                kern_char = word[char].lower()
                if n > 1:
                    skip_count = n - 1
            else:
                if word[char] in ALPHABET:
                    i = ALPHABET.index(word[char])
                    self._draw_pixbuf(self._letters[i].images[0],
                                      self._x_pos, self._y_pos,
                                      canvas, gc)
                    kern_char = word[char]

            if kern_char in KERN:
                self._x_pos += self._offset * KERN[kern_char]
            else:
                self._x_pos += self._offset

        self._final_x = self._x_pos
        # Put a space after each word
        if self._x_pos > self._margin:
            self._x_pos += int(self._offset / 1.6)

    def _draw_pixbuf(self, pixbuf, x, y, canvas, gc):
        ''' Draw a pixbuf onto the canvas '''
        w = pixbuf.get_width()
        h = pixbuf.get_height()
        canvas.images[0].draw_pixbuf(gc, pixbuf, 0, 0, int(x), int(y))
        self.invalt(x, y, w, h)

    def _increment_xy(self, y):
        ''' Increment the xy postion for drawing the next phrase, with
        left-justified alignment. '''
        return 10, self._lead + y

    def _button_press_cb(self, win, event):
        ''' Either a card or list entry was pressed. '''
        win.grab_focus()
        x, y = map(int, event.get_coords())

        if self._looking_at_word_list:
            self._goto_page = int(y * 1.0 / self._lead)
        else:
            spr = self._sprites.find_sprite((x, y))
            self._press = spr
            self._release = None
        return True

    def _button_release_cb(self, win, event):
        ''' Play a sound or jump to a card as indexed in the list. '''
        win.grab_focus()

        if self._looking_at_word_list:
            self._looking_at_word_list = False
            if self._goto_page > self.page:
                for _i in range(self._goto_page - self.page):
                    self.page += 1
                    self.new_page()
            else:
                self.page = self._goto_page
                self.new_page()
        else:
            x, y = map(int, event.get_coords())
            spr = self._sprites.find_sprite((x, y))
            if spr == self._cards[self.page]:
                if self.page < len(self._card_data):
                    if os.path.exists(os.path.join(
                            os.path.abspath('.'), 'sounds',
                            self._sound_data[self.page])):
                        play_audio_from_file(self, os.path.join(
                                os.path.abspath('.'), 'sounds',
                                self._sound_data[self.page]))

    def _keypress_cb(self, area, event):
        ''' No keyboard shortcuts at the moment. Perhaps jump to the page
        associated with the key pressed? '''
        return True

    def _expose_cb(self, win, event):
        ''' When asked, we need to refresh the screen. '''
        self._sprites.redraw_sprites()
        return True

    def _destroy_cb(self, win, event):
        ''' Make a clean exit. '''
        gtk.main_quit()

    def invalt(self, x, y, w, h):
        ''' Mark a region for refresh '''
        self._canvas.window.invalidate_rect(
            gtk.gdk.Rectangle(int(x), int(y), int(w), int(h)), False)

    def load_level(self, path):
        ''' Load a level (CSV) from path '''
        self._card_data = []
        self._color_data = []
        self._msg_data = []
        self._sound_data = []
        self._word_data = []
        # f = file(path, 'r')
        f = codecs.open(path, encoding='utf-8')
        for line in f:
            if len(line) > 0 and line[0] not in '#\n':
                words = line.split(', ')
                if not words[0] in '-+':
                    self._card_data.append([words[0],
                        words[1].replace('-', ', ')])
                    if words[2].count('#') > 1:
                        self._color_data.append(
                            [words[2].split('/'), words[3]])
                    else:
                        self._color_data.append(
                            [words[2], words[3]])
                    if len(self._msg_data) == 0:
                        self._msg_data.append(FIRST_CARD)
                    elif words[4] == 'vowel':
                        self._msg_data.append(VOWEL)
                    elif words[4] == 'light':
                        self._msg_data.append(LIGHT)
                    elif words[4] == 'consonant':
                        self._msg_data.append(CONSONANT)
                    elif words[4] == 'double':
                        self._msg_data.append(DOUBLE)
                    else:
                        print 'unknown message id %s' % (words[4])
                        self._msg_data.append(CONSONANT)
                    self._sound_data.append(words[5])
                if words[0] == '+':
                    self._test_data = words[6]
                else:
                    self._word_data.append(words[6])
        f.close()

        self._clear_all()
        self._cards = []
        self._double_cards = []
        self._colored_letters = []

    def _clear_all(self):
        ''' Hide everything so we can begin a new page. '''
        self._hide_cards()
        if self._picture is not None:
            self._picture.set_layer(0)

    def _hide_cards(self):
        ''' Hide any cards that might be around. '''
        for card in self._cards:
            card.set_layer(0)
        for card in self._double_cards:
            card.set_layer(0)


def svg_str_to_pixbuf(svg_string):
    ''' Load pixbuf from SVG string. '''
    pl = gtk.gdk.PixbufLoader('svg')
    pl.write(svg_string)
    pl.close()
    pixbuf = pl.get_pixbuf()
    return pixbuf


def image_file_to_pixbuf(file_path, scale):
    ''' Load pixbuf from file '''
    return gtk.gdk.pixbuf_new_from_file_at_size(
        file_path, int(scale * 320), int(scale * 240))

