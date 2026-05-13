
# Draw Animated with Staged Incremental Blitting
# Copyright (c) 2023 stuart.lynne@gmail.com
# Made available under the MIT license.
# See LICENSE file for details.

import sys
import matplotlib.pyplot as plt
import numpy as np
from enum import Enum
from time import time, sleep, perf_counter
from matplotlib.axis import XAxis, YAxis
from matplotlib.legend import Legend
from matplotlib.spines import Spine
import matplotlib 


class DrawTimes:
    def __init__(self,):
        self._drawtimes = {}
        self._drawcount = {}
        self._drawlast = {}
        self._drawtypes = {}
        self.t0 = None
        self.name = self.type = None
        self.elapsed = 0

    def __enter__(self):
        self.t0 = perf_counter()
        self.name = None
        return self


    def __exit__(self, type, value, traceback):
        #print('drawtimes[%s].__exit__ name: %s' % (id(self), self.name), file=sys.stderr)
        if self.name is None:
            return
        t1 = perf_counter()
        self.elapsed = t1 - self.t0
        if self.name not in self._drawtimes:
            self._drawtimes[self.name] = self._drawlast[self.name] = 0. 
            self._drawcount[self.name] = 0
            self._drawtypes[self.name] = None
        self._drawtimes[self.name] += self.elapsed
        self._drawlast[self.name] = t1
        self._drawcount[self.name] += 1
        self._drawtypes[self.name] = self.type
        self.name = self.type = None
        
    def print_summary(self, name=''):
        # show draw times
        total_time = sum(self._drawtimes.values())
        #print('draw_animated[%s] total time: %7.2f' % (id(self), total_time), file=sys.stderr)
        drawinfo = [(
            self._drawtimes[k] / self._drawcount[k] if self._drawcount[k] > 0 else 0.,  # avg - average time per draw
            self._drawtimes[k],                        # total - total time spent drawing 
            self._drawcount[k],                        # count - number of times drawn 
            str(k),                                    # name - name of artist 
            self._drawtypes[k],                        # type - type of artist
        ) for k in self._drawtimes.keys()]
        total_pc = 0    
        for avg, total, count, artist, type in sorted(drawinfo, key=lambda x: x[1], reverse=True):
            pc = 100.0*total/total_time
            total_pc += pc
            if count > 0:
                print('draw_animated %s %5d | %7.2f %4.1f%% %4.0f%% | %7.2f | %10s | %s' % (
                    name, count, total, pc, total_pc, avg, type, artist,),  file=sys.stderr) 


# Draw Animated with Blitting
# This class is used to draw animated artists on a matplotlib axes using blitting.
# It is designed to be used in a loop, where each iteration of the loop will draw
# one or more artists.  The loop should continue until draw_animated() returns False.
#
# The intent is to allow the GUI event loop to run between each call to draw_animated()
# to reduce latency and improve responsiveness of the GUI.
#
class DrawAnimated:

    class DrawState(Enum):
        CREATED = 0
        OPEN = 1
        START = 2
        STATIC = 3 
        DYNAMIC = 4
        BLIT = 5
        CLEANUP = 6
        FLUSH = 7
        DONE = 8
        CLOSED = 9
        RESET = 10
        WAITING = 11


    def xprint(self, msg, always=False):
        if always or self.debug:
            print('draw_animated[%s:%8.4f] %s %s' % (id(self.fig), perf_counter(), self.draw_state.name, msg), file=sys.stderr, )


    def __init__(self, fig, name=''):
        self.fig = fig
        self.debug = False
        self.xprint('fig: %s' % (id(fig)), always=False)
        self._bg_base = self._bg_static = None
        self.debug = False
        self.current_animated_artists = []
        self._mpl_connect = []
        self.draw_state = self.DrawState.CREATED
        self.blit_times = []
        self.static_draws = self.dynamic_draws = self.avg_static_draws = self.avg_dynamic_draws = self.static_artists = self.dynamic_artists = 0
        self.first = True
        self._fps = 0
        self.drawtimes = DrawTimes()
        self.wait_count = 0
        self.name = name

    def reset(self, info, ):
        self.xprint('', )
        if self.draw_state == self.DrawState.WAITING:
            return
        self.draw_state = self.DrawState.RESET
        self._bg_static = None
        self.xprint('%s reset bg_static ------------------ %s' % (info, self.draw_state), always=False )

    def _on_resize(self, event):
        self._bg_base = self._bg_static = None
        if self.draw_state != self.DrawState.START:
            self.draw_state = self.DrawState.WAITING
        self.wait_count = 0
        self.xprint('', )
        self.xprint('reset resize_event reset bg_base bg_static ------------------ %s' % (self.draw_state), always=False )
        #self.reset('on_resize')

    def _on_draw_event(self, event):
        #self.reset('on_draw_event')
        self.draw_state = self.DrawState.RESET
        self._bg_static = None
        self.xprint('', )
        self.xprint('reset draw_event reset bg_static ------------------ %s' % (self.draw_state), always=False )
        #pass

    def _on_close_event(self, event):
        pass

    def add_static_artists(self, artists):
        self.extra_static_artists += artists

    def add_static_artist(self, artist):
        self.extra_static_artists.append(artist)

    def open(self, xaxis_dynamic=False, yaxis_dynamic=False, extra_static_artists=[], debug=False, name=None, ):
        self.draw_state = self.DrawState.OPEN
        self.xaxis_dynamic = xaxis_dynamic
        self.yaxis_dynamic = yaxis_dynamic
        self.extra_static_artists = extra_static_artists
        self.debug = debug
        self.draw_state = self.DrawState.START
        if name is not None:
            self.name = name
        try:
            for e in self._mpl_connect:
                self.fig.figure.canvas.mpl_disconnect(e)
        except:
            pass
        self._mpl_connect = []

        self.bg_base = self.static = None
        self._mpl_connect.append(self.fig.canvas.mpl_connect('resize_event', self._on_resize))
        self._mpl_connect.append(self.fig.canvas.mpl_connect('draw_event', self._on_draw_event))
        self._mpl_connect.append(self.fig.canvas.mpl_connect('close_event', self._on_close_event))

    def close(self):
        for e in self._mpl_connect:
            self.fig.figure.canvas.mpl_disconnect(e)
        self._mpl_connect = []
        self.extra_static_artists = []

    # animate_chrome - helper function to animate the chrome of the axes
    def animate_chrome(self, ax, name='', title=None, set_label=True, ):
        # animate the title, the axes and the spines
        if title is not None:
            ax.set_title(title, animated=True, )
        for n, a in ax._axis_map.items():
            a.set_animated(True)
            # Newer Matplotlib rejects Axis.set_label() here because that API is
            # for axis-title text, not an artist identity. Keep a private label
            # for DrawAnimated bookkeeping instead.
            a._label = f"{name}-{n}axis"
        for n, s in ax.spines.items():
            s.set_animated(True)
            s.set_label(f"{name}-{n}-spine")
        ax.patch.set_animated(True)
        #ax.patch.set_alpha(0.2)

    # get_label - helper function to get the label of an artist, needed to handle XAxis and YAxis
    def get_label(self, a):
        def get_axis_label(a, name):
            try:
                return a._label
            except:
                return name
        if type(a) is XAxis:
            return get_axis_label(a, 'XAxis')
        if type(a) is YAxis:
            return get_axis_label(a, 'YAxis')
        return a.get_label()

    # draw_artists - helper function to draw a list of artists
    def draw_artists(self, draw_list, info: str = None, ):
        self.xprint("draw_artists: draw_list: %s" % (len(draw_list)), )
        while len(draw_list) > 0:
            a = draw_list.pop(0)
            self.xprint("draw_artists: draw: %s %s %s %s" % (id(a), info, self.get_label(a), a), )
            #if a not in self.current_animated_artists:
            #    continue
            self.fig.draw_artist(a)
            #self.fig.figure.canvas.blit(self.fig.figure.bbox)
            return f"{id(a)} {self.get_label(a)}"
        return None

    # draw - do the next step of the animation
    def draw(self, flush_events=False, ):

        self.xprint(f"draw: draw_state: {self.draw_state}", always=False,)
        if self.draw_state == self.DrawState.WAITING:
            sleep(.2)
            return 'waiting', None, self.draw_state.name

        if self.draw_state in [self.DrawState.START, self.DrawState.STATIC, self.DrawState.DYNAMIC, ]: 

            # Get the list of animated artists that are currently visible, this needs to be done
            # each time because the list of artists can change dynamically. Effectively new artists
            # are ignored until the next cycle of drawing is started, but removed artists are 
            # immediately ignored.
            # N.b. There may be other artists for other types of plots, this code works in my use case. 
            # N.b. Patch objects need to be drawn before the other static artists, do we need dynamic patches?
            # YMMV.
            static_dict = {}
            dynamic_dict = {}
            patch_dict = {}
            for axes in self.fig.get_children():
                #self.xprint(f"draw: axes: {axes.get_label()}", )
                if type(axes) is plt.Axes:
                    for a in axes.get_children():
                        #self.xprint(f"draw: a: {a.get_label()} animated: {a.get_animated()} visible: {a.get_visible()}", )
                        if a.get_animated() and a.get_visible():
                            if a in [axes.patch,]:
                                patch_dict[id(a)] = a
                            elif a in self.extra_static_artists:
                                static_dict[id(a)] = a
                            elif (type(a) is XAxis and not self.xaxis_dynamic) or (type(a) is YAxis and not self.yaxis_dynamic) or type(a) is Legend or type(a) is Spine:
                                static_dict[id(a)] = a
                            elif a in [axes.title, axes._left_title, axes._right_title,]:
                                static_dict[id(a)] = a
                            else:
                                dynamic_dict[id(a)] = a

            #static_animated_artists = [a for a in static_dict.values()] if fig._bg_static is None else []
            static_animated_artists = [a for a in patch_dict.values()] + [a for a in static_dict.values()] 
            dynamic_animated_artists = [ a for a in dynamic_dict.values()]
            current_animated_artists = static_animated_artists + dynamic_animated_artists
            self.static_artists = len(static_animated_artists) 
            self.dynamic_artists = len(dynamic_animated_artists) 
            self.xprint("draw_animated: static_artists: %s dynamic_artists: %s" % (self.static_artists, self.dynamic_artists), always=False,)

            if self.draw_state == self.DrawState.START:
                self.static_animated_artists = static_animated_artists
                self.dynamic_animated_artists = dynamic_animated_artists
            if self.first or self._bg_static is None or self._bg_base is None:
                self.xprint(f"draw_animated: static_animated_artists: {len(static_animated_artists)}")
                for a in static_animated_artists:
                    self.xprint(f"draw_animated[{id(a)}]: static_animated_artists: {a.get_label()}")
                self.xprint(f"draw_animated: dynamic_animated_artists: {len(dynamic_animated_artists)}")
                for a in dynamic_animated_artists:
                    self.xprint(f"draw_animated[{id(a)}] dynamic_animated_artists: {a.get_label()}")
                self.first = False
            #self.xprint("draw_animated: current_animated_artists: %s" % (len(current_animated_artists)), )
            #self.xprint("draw_animated: static_animated_artists: %s" % (len(static_animated_artists)), )
            #self.xprint("draw_animated: dynamic_animated_artists: %s" % (len(dynamic_animated_artists)), )

        # RESET - clear the static background so it will be redrawn
        if self.draw_state == self.DrawState.RESET:
            self.draw_state = self.DrawState.START
            #self._bg_base = None
            self._bg_static = None
            return 'reset', None, self.draw_state.name

        # START - ensure we have base background and determine if we need to draw static artists
        # or can just draw the dynamic artists
        if self.draw_state == self.DrawState.START:

            self.xprint('_bg_base: %s _bg_static: %s' % (self._bg_base, self._bg_static), )
            self.xprint("len(static_animated_artists): %s len(dynamic_animated_artists): %s" % (len(static_animated_artists), len(dynamic_animated_artists)), )
            self.dynamic_draws = self.static_draws = 0
            # if we don't have a static background, save the base and draw the static artists
            if self._bg_base is None:
                self.xprint('reset bg_base: %s bg_static: %s' % (self._bg_base, self._bg_static), always=False)
                self._bg_base = self.fig.figure.canvas.copy_from_bbox(self.fig.figure.bbox)
                self._bg_static = None
                self.draw_state = self.DrawState.STATIC
                #sleep(6)
                self.xprint('', )
                self.xprint('bg_base = copy_from_bbox <<<<<<<<<<<<<<<<', always=False)
                self.xprint('', )
                return 'bg_base = copy_from_bbox', None, self.draw_state.name
            
            # if we do not have a saved static background, then we need to draw the static artists
            if self._bg_static is None:
                # if we don't have a static background, restore the base, draw the static artists and
                # save the background
                self.draw_state = self.DrawState.STATIC
                self.fig.canvas.restore_region(self._bg_base)
                self.xprint('restore_region bg_base <<<<<<<<<<<<<<<< STATIC', always=False)
                return 'restore_region bg_base', None, self.draw_state.name
            
            # if we have a static background, then we need to restore it and draw the dynamic artists
            self.fig.canvas.restore_region(self._bg_static)
            self.draw_state = self.DrawState.DYNAMIC
            self.xprint('restore_region bg_static <<<<<<<<<<<<<<<< DYNAMIC', always=False)
            return 'restore_region bg_static', None, self.draw_state.name
    
        # STATIC - draw the static artist and then save the background
        if self.draw_state == self.DrawState.STATIC:
            self.xprint("draw_animated: static_animated_artists: %s" % (len(self.static_animated_artists)), )
            artist = self.draw_artists(self.static_animated_artists, info='static')
            if artist is not None:
                self.static_draws += 1
                return artist, 'static', self.draw_state.name

            self._bg_static = self.fig.figure.canvas.copy_from_bbox(self.fig.figure.bbox)
            self.xprint('static_draws: %s' % (self.static_draws, ), always=False)
            self.xprint('bg_static = copy_from_bbox <<<<<<<<<<<<<<<<', always=False)

            self.draw_state = self.DrawState.DYNAMIC
            return 'bg_static = copy_from_bbox', None, self.draw_state.name

        # DYNAMIC - draw the dynamic artists
        if self.draw_state == self.DrawState.DYNAMIC:
            self.xprint("draw_animated: dynamic_animated_artists: %s" % (len(self.dynamic_animated_artists)), )
            artist = self.draw_artists(self.dynamic_animated_artists, info='dynamic' )
            if artist is not None:
                self.dynamic_draws += 1
                return artist, 'dynamic', self.draw_state.name
            self.draw_state = self.DrawState.BLIT
            self.xprint('dynamic_draws: %s' % (self.dynamic_draws, ), always=False)
            return 'dynamic', None, self.draw_state.name

        # BLIT - blit the canvas
        if self.draw_state == self.DrawState.BLIT:
            self.fig.figure.canvas.blit(self.fig.figure.bbox)
            self.draw_state = self.DrawState.CLEANUP
            return 'blit', None, self.draw_state.name

        # CLEANUP - cleanup the blit times and calculate the fps
        if self.draw_state == self.DrawState.CLEANUP:
            self.draw_state = self.DrawState.FLUSH if flush_events else self.DrawState.DONE
            current_time = perf_counter()
            self.blit_times.append((current_time, self.static_draws, self.dynamic_draws))
            delete_time = current_time - 120.
            blit_times = [ t for t in self.blit_times if t[0] > delete_time]
            self.blit_times = blit_times
            elapsed = self.blit_times[-1][0] - self.blit_times[0][0]
            self._fps = len(self.blit_times) / elapsed if elapsed > 0. else 0.
            self.avg_static_draws = sum([t[1] for t in self.blit_times]) / len(self.blit_times)
            self.avg_dynamic_draws = sum([t[2] for t in self.blit_times]) / len(self.blit_times)
            self.fps_info = (self._fps, self.static_artists, self.dynamic_artists, self.avg_static_draws, self.avg_dynamic_draws)
            self.xprint('static_draws: %s dynamic_draws: %s' % (self.static_draws, self.dynamic_draws, ), always=False)
            self.xprint('cleanup bg_base: %s bg_static: %s' % (self._bg_base, self._bg_static), always=False)
            return 'cleanup', None, self.draw_state.name

        if self.draw_state == self.DrawState.FLUSH:
            # optionally let the GUI event loop process anything it has to do
            self.fig.canvas.flush_events()
            self.draw_state = self.DrawState.DONE
            return 'FLUSH', None, self.draw_state.name

        if self.draw_state == self.DrawState.DONE:
            self.draw_state = self.DrawState.START
            return None, None, self.draw_state.name

    def xdraw_loop(self, pause_time=0.01, sleep_time=0., flush_events=True ):
        elapsed = 0
        while True:
            with self.drawtimes as dt:
                dt.name, dt.type, next_state = self.draw(flush_events=flush_events,)
            #print('draw: %s %s %s' % (dt.name, dt.type, next_state), file=sys.stderr)
            if dt.name is None:
                return True
            elapsed += self.drawtimes.elapsed
            if elapsed > pause_time:
                return False
            if sleep_time > 0.:
                sleep(sleep_time)

    # draw_loop - call draw until it returns None then return True,
    # if the the elapsed time is greater than pause_time sleep or return False
    def draw_loop(self, pause_time=0.01, flush_events=True, sleep_time=0.): 
        elapsed = 0
        while True:
            with self.drawtimes as dt:
                dt.name, dt.type, next_state = self.draw(flush_events=flush_events, )
                if dt.name is None:
                    return True
                elapsed += dt.elapsed 
                #if next_state == self.DrawState.WAITING.name:
                #    sleep(1)
                #    return False
                if elapsed > 0.01:
                    if sleep_time > 0.:
                        sleep(sleep_time)
                    else:
                        return False
            #count += 1
            #tmc.count = count
            #if draw_time is None:
            #    return False
            #self.print('draw_animated[%s] draw_time: %s elapsed: %s' % (msg, round(draw_time[0], 5), round(elapsed,5)), )



    def print_summary(self, name=None):
        self.drawtimes.print_summary(name if name is not None else self.name)


# ########################################################################################################

# an example of using DrawAnimated to animate a matplotlib plot
#
if __name__ == "__main__":

    print('matplotlib version: %s' % (matplotlib.__version__), )
    print('matplotlib backend: %s' % (matplotlib.get_backend()), )

    # create a mosaic 2 x 2 grid of subplots, 
    fig, axes_dict = plt.subplot_mosaic([['a', 'b'], ['c', 'd']], constrained_layout=True, figsize=(8, 8))

    # setup 4 lines and 2 annotations on each subplot axes, ensure everything is animated
    lines = {n: {} for n in axes_dict.keys()}
    annotations = { a: {'frame_number': None, 'fps': None} for a in axes_dict.keys()}
    legends = {n: None for n in axes_dict.keys()}
    colors = ['red', 'blue', 'green', 'brown']

    drawanimated = DrawAnimated(fig, )
    drawanimated.open(xaxis_dynamic=False, yaxis_dynamic=False, extra_static_artists=[], debug=False, name='test', )
    drawtimes = DrawTimes()

    for name, ax in axes_dict.items():
        drawanimated.animate_chrome(ax, name=name, title=f"Draw Animated Incremental {name}", )
        # create the 4 line plots
        x = np.linspace(0, 2 * np.pi, 100)
        for c in colors:
            line, = ax.plot(x, np.sin(x), animated=True, label=f"{name}-{c}", color=c, )
            lines[name][c] = line

        # create the 2 annotations
        for annotation, xytext in [('frame_number', (10, -10)), ('fps', (200, -10))]:
            annotations[name][annotation] = ax.annotate( 
                annotation, (0, 1), xycoords="axes fraction", xytext=xytext, 
                textcoords="offset points", ha="left", va="top", label=f"{annotation}-an", 
                animated=True, )

        # create the legend, note that the ax.legend call does not take the animated parameter, 
        # need to set it explicitly
        leg = ax.legend(handles=lines[name].values(), loc='lower right', )
        leg.set_animated(True)
        leg.set_label('legend')
        legends[name] = leg


    # make sure our window is on the screen and drawn
    fig.show()
    #plt.pause(0.001)

    start_time = time()
    frame_count = 0
    divisor = 100
    multiplier = 1
    resets = 0 
    reset = False
    force = False
    for j in range(500):

        if j % 80 == 0:
            multiplier *= 1.2
        
        for i, (name, ax) in enumerate(axes_dict.items()):
            ymin = []
            ymax = []
            for k, (color, line) in enumerate(lines[name].items()):
                offset = k * 10
                ydata = np.sin(x + offset + (j / divisor) * np.pi / (k+1)) * multiplier 
                ymin.append(min(ydata))
                ymax.append(max(ydata))
                line.set_ydata(ydata)
            annotations[name]['frame_number'].set_text("frame: %d" % (frame_count,))
            elapsed = time() - start_time
            if elapsed > 0:
                annotations[name]['fps'].set_text("fps: %3.1f" % (frame_count / elapsed))

            if j % 80 == 0:

                min_y = min(ymin)
                max_y = max(ymax)
                ylims = ax.get_ylim()

                if min_y < ylims[0] or max_y > ylims[1]:
                    ax.set_ylim(min_y, max_y)
                    ax.set_ylim(min_y, max_y)
                    ax.set_xlim(0, 2 * np.pi)
                    reset = True
                #ax.patch.set_alpha(0.2)
                ax.set_facecolor('white' if j % 160 == 0 else 'grey')
                

        if force or  reset:
            resets += 1
            reset = False
            for name, ax in axes_dict.items():
                ax.set_title(f"Draw Animated Incremental {name} {resets}")
            #self._draw_reset = True
            drawanimated.reset('main')

        # update, this is a loop so GUI can process events
        drawanimated.draw_loop(pause_time=0.01, sleep_time=0.001 )
        frame_count += 1
        fig.canvas.flush_events()
        print('frame: %d' % (frame_count,), file=sys.stderr) 
        sleep(.0001)

    drawanimated.close()

    drawanimated.print_summary()

