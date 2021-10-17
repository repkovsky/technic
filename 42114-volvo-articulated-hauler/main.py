# Remote is currently in beta. This program only works with firmware
# installed from <https://beta.pybricks.com>.

from pybricks.pupdevices import Motor, Remote
from pybricks.parameters import Port, Button, Color
from pybricks.tools import wait

# control buttons swapping
LEFT_STEER_RIGHT_DRIVE = True

# set gearbox to AUTO mode at startup?
INIT_GEARBOX_AUTO = True

# steering settings
STEER_ANGLE = 60
STEER_SPEED = 1000

class Gearbox:
    # if speed is stable above, automatic gearbox will increase gear
    HI_SPEED = 1750
    # if speed is stable below, automatic gearbox will decrease gear
    LO_SPEED = 800
    # time [ms] after gearbox switches to 1st gear when drive remains idle
    GEAR_RESET_TIMEOUT = 2000
    # time [ms] of speed stability measurement before automatic gear change
    STABLE_SPEED_TIME = 800
    # speed measurement smoothing factor
    SMOOTHING = 0.05
    # colors of gearbox state indicator LED for automatic (True) and manual (False)
    # [gear 1, gear 2, gear 3, dumper]
    POS_COLOR = {True: [Color.CYAN, Color.BLUE, Color.MAGENTA, Color.GREEN],
                 False: [Color.ORANGE,  Color(h=15, s=100, v=100),
                         Color(h=5, s=100, v=100), Color.GREEN]}
    POS_ANGLE = [90, 0, -90, -180]

    def __init__(self, remote):
        # initialize class properties
        self.remote = remote
        self.speed_timer = 0
        self.idle_timer = 0
        self.speed = 0
        # initialize L motor
        self.gearbox = Motor(Port.B)
        self.gearbox.control.limits(speed=2000, acceleration=3000)
        # callibrate gearbox motor by finding its physical rotation limit; 
        # use small duty_limit to avoid twisting 12-axle and measurement error
        stalled_angle = self.gearbox.run_until_stalled(500, duty_limit=10)
        # round to multiple of 90 degrees and subtract angle of physical block (90deg)
        base_angle = 90*round(stalled_angle/90)-90
        # adjust settings of possible motor positions
        self.POS_ANGLE = [p+base_angle for p in self.POS_ANGLE]
        # set defaults
        self.pos = 0
        self.prev_gear = 0
        self.set_auto(INIT_GEARBOX_AUTO)

    def set_position(self, pos):
        # limit positions to range 0,1,2,3
        pos = min(3, max(pos, 0))
        # apply new position if it is different from current one
        if self.pos != pos:
            # set remote control light according to mode and position
            self.remote.light.on(self.POS_COLOR[self.auto][pos])
            # rotate gearbox to angle that corresponds position
            self.gearbox.run_target(2000, target_angle=self.POS_ANGLE[pos], wait=True)
            if pos == 3:
                # remeber gear used before switching to dumper
                self.prev_gear = self.pos
            self.pos = pos
            print('Position:', pos, self.gearbox.angle(), 
                  'error:', self.POS_ANGLE[pos]-self.gearbox.angle(),
                  'auto:', bool(self.auto))

    def dumper(self):
        # return whether gearbox is set to drive dumper
        return self.pos == 3

    def set_auto(self, auto):
        # set AUTO/MANUAL mode and update control light
        self.auto = auto
        self.remote.light.on(self.POS_COLOR[self.auto][self.pos])

    def get_auto_gear(self, speed):
        # returns changed gear if speed is stable below/above LO_SPEED/HI_SPEED threshold
        if self.auto and not self.dumper():
            # basic low-pass filtering (exponential smoothing)
            self.speed += self.SMOOTHING*(abs(speed)-self.speed)
            wait(10)
            if self.LO_SPEED < self.speed < self.HI_SPEED:
                # speed in medium range, reset timer
                self.speed_timer = 0
            else:
                # speed out of medium range, increase time of measurement
                self.speed_timer += 10
                if self.speed_timer > self.STABLE_SPEED_TIME:
                    # speed is stable - reset timer
                    self.speed_timer = 0
                    # depending on speed and current position,
                    # return lower, higher or None gear (no change) 
                    if self.pos > 0 and self.speed < self.LO_SPEED:
                        return self.pos - 1
                    elif self.pos < 2 and self.speed > self.HI_SPEED:
                        return self.pos + 1
        return None

    def idle(self, persists):
        if persists:
            # increase idle time
            wait(1)
            self.idle_timer += 1
            if self.auto and self.idle_timer >= self.GEAR_RESET_TIMEOUT:
                # reset gearbox to lowest gear
                self.idle_timer = 0
                gearbox.set_position(0)
        else:
            self.idle_timer = 0

class Key:
    def __init__(self):
        # variables to store current and previous state of buttons
        self.now_pressed = []
        self.prev_pressed = []
    
    def update(self, remote):
        # copy list of keys pressed during last update
        self.prev_pressed = list(self.now_pressed)
        # update list of pressed keys
        self.now_pressed = remote.buttons.pressed()

    def pressed(self, key):
        # return whether key is now pressed
        return key in self.now_pressed

    def released(self, key):
        # return keys which were released after last update
        return key in self.prev_pressed and key not in self.now_pressed

def direction(positive, negative):
    # return resultant value of two boolean directions
    return int(bool(positive)) - int(bool(negative))

if __name__ == '__main__':
    # Connect to the remote.
    remote = Remote()
    print('Remote connected.')

    # initialize driving motor
    drive = Motor(Port.A)

    # initialize steering motor
    steer = Motor(Port.D)
    kp, ki, _, _, _ = steer.control.pid()
    steer.control.limits(speed=STEER_SPEED, acceleration=3000)
    steer.control.pid(kp=kp*8, ki=ki*8, integral_range=60)

    # initialize gearbox
    gearbox = Gearbox(remote)

    # initialize remote keys
    key = Key()
    if LEFT_STEER_RIGHT_DRIVE:
        BUTTON_DRIVE_FWD, BUTTON_DRIVE_BACK = Button.RIGHT_PLUS, Button.RIGHT_MINUS
        BUTTON_STEER_LEFT, BUTTON_STEER_RIGHT = Button.LEFT_PLUS, Button.LEFT_MINUS
    else:
        BUTTON_DRIVE_FWD, BUTTON_DRIVE_BACK = Button.LEFT_PLUS, Button.LEFT_MINUS
        BUTTON_STEER_LEFT, BUTTON_STEER_RIGHT = Button.RIGHT_PLUS, Button.RIGHT_MINUS
    
    # main loop
    while True:
        key.update(remote)

        # gearbox control
        if key.released(Button.LEFT):
            # manual - change to lower gear; auto - switch to driving
            new_pos = gearbox.prev_gear if gearbox.auto else gearbox.pos-1
            gearbox.set_position(new_pos)
        elif key.released(Button.RIGHT):
            # manual - change to higher gear/dumper; auto - switch to dumper
            new_pos = 3 if gearbox.auto else gearbox.pos+1
            gearbox.set_position(new_pos)
        elif key.released(Button.CENTER):
            # switch gearbox mode to the other one
            gearbox.set_auto(not gearbox.auto)
        
        # drive control
        drive_direction = direction(key.pressed(BUTTON_DRIVE_FWD),
                                    key.pressed(BUTTON_DRIVE_BACK))
        if drive_direction in [-1,1]:
            auto_gear = gearbox.get_auto_gear(drive.speed())
            if auto_gear is not None:
                # stop motor to allow smooth gear switch
                drive.stop()
                gearbox.set_position(auto_gear)
            # for dumper direction of rotation must be inverted
            invert = 1 if gearbox.dumper() else -1
            drive.dc(invert*drive_direction*100.0)
            # report active drive
            gearbox.idle(False)
        else:
            drive.stop()
            # report idle drive if not set to dumper
            gearbox.idle(not gearbox.dumper())
        
        # steering control
        steer_direction = direction(key.pressed(BUTTON_STEER_RIGHT),
                                    key.pressed(BUTTON_STEER_LEFT))
        steer.run_target(STEER_SPEED, steer_direction*STEER_ANGLE, wait=False)
