"""Shadow Arena: Ashes of the Bell. Offline Android action RPG (Kivy)."""
import json
import math
import os
import random
from dataclasses import dataclass

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle, Triangle
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.metrics import dp
from kivy.core.audio import SoundLoader

WORLD_W, WORLD_H = 1500, 1100
CHAPTERS = [
    {"name": "I. Проклятая деревня", "goal": 9, "boss": "Хранитель Могил", "enemy": "Мертвец", "story": "Колокол умолк три ночи назад. Жители исчезли, а мёртвые восстали. Отыщи хранителя кладбища и забери первую печать."},
    {"name": "II. Забытые катакомбы", "goal": 13, "boss": "Костяной Пророк", "enemy": "Скелет", "story": "Первая печать открыла путь под землёй. Костяной Пророк хранит вторую печать в катакомбах."},
    {"name": "III. Пепельный собор", "goal": 17, "boss": "Владыка Пепла", "enemy": "Пепельный демон", "story": "Две печати ведут в собор. Останови Владыку Пепла, пока он не пробудил древний колокол."},
]
SPELLS = [
    ("ОГОНЬ", 16, 0.42, (1.0, .39, .12)),
    ("ЛЁД", 28, 2.8, (.38, .79, 1)),
    ("МОЛНИЯ", 38, 4.2, (.85, .72, 1)),
    ("ЛЕЧЕНИЕ", 45, 7.5, (.36, 1, .59)),
]
TALENTS = [
    ('Пиромантия', 'Урон огня +15% за ранг', 5),
    ('Ледяное сердце', 'Лёд замедляет дольше', 5),
    ('Грозовой зов', 'Урон молнии +12% за ранг', 5),
    ('Источник маны', 'Максимум маны +20 за ранг', 5),
    ('Кровавый оберег', 'Здоровье +18 за ранг', 5),
    ('Быстрые руны', 'Сокращение перезарядки', 5),
]
RARITY = [("Обычный", (0.8, .8, .75)), ("Магический", (.4, .67, 1)), ("Редкий", (1, .81, .32)), ("Легендарный", (1, .43, .13))]


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def distance(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])


@dataclass
class Enemy:
    x: float
    y: float
    hp: float
    maxhp: float
    speed: float
    damage: float
    boss: bool = False
    slow: float = 0
    attack_cd: float = 0
    shoot_cd: float = 0


class Arena(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.labels = []
        self.touches = {}
        self.joy_id = None
        self.joy = (0, 0)
        self.action_rects = {}
        self.message = ""
        self.message_time = 0
        self.overlay = None
        self.start_new()
        Clock.schedule_interval(self.tick, 1/30)
        self.bind(size=lambda *_: self.draw(), pos=lambda *_: self.draw())

    def save_path(self):
        return os.path.join(App.get_running_app().user_data_dir, 'save.json')

    def start_new(self):
        self.chapter = 0
        self.level = 1
        self.talents = [0]*len(TALENTS)
        self.skill_points = 0
        self.xp = 0
        self.kills = 0
        self.gold = 0
        self.hp = 110.0
        self.mana = 160.0
        self.x, self.y = WORLD_W/2, WORLD_H/2
        self.gear = {"staff": 0, "robe": 0, "ring": 0}
        self.bag = []
        self.skill_cd = [0.] * 4
        self.enemies = []
        self.projectiles = []
        self.particles = []
        self.pickups = []
        self.spawn_timer = 0
        self.autosave_timer = 45.0
        self.boss_spawned = False
        self.boss_dead = False
        self.finished = False
        self.paused = True
        self.overlay = "menu"
        self.random_map()
        self.draw()

    def random_map(self):
        rng = random.Random(2026 + self.chapter)
        self.obstacles = []
        for _ in range(44):
            x, y = rng.randrange(65, WORLD_W-65), rng.randrange(65, WORLD_H-65)
            if distance((x,y), (WORLD_W/2,WORLD_H/2)) > 150:
                self.obstacles.append((x,y,rng.randrange(18,44)))

    @property
    def max_hp(self):
        return 110 + (self.level-1)*17 + self.gear['robe']*12 + self.talents[4]*18

    @property
    def max_mana(self):
        return 160 + (self.level-1)*12 + self.talents[3]*20

    @property
    def damage(self):
        return 20 + (self.level-1)*5 + self.gear['staff']*7 + self.gear['ring']*4

    def save(self, silent=False):
        try:
            os.makedirs(os.path.dirname(self.save_path()), exist_ok=True)
            data = {k:getattr(self,k) for k in ('chapter','level','xp','kills','gold','hp','mana','x','y','gear','bag','boss_spawned','boss_dead','finished','talents','skill_points')}
            with open(self.save_path(), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            if not silent:
                self.say('Игра сохранена')
        except Exception:
            self.say('Не удалось сохранить игру')

    def load(self):
        try:
            with open(self.save_path(), encoding='utf-8') as f:
                data = json.load(f)
            self.start_new()
            for k in ('chapter','level','xp','kills','gold','hp','mana','x','y','gear','bag','boss_spawned','boss_dead','finished','talents','skill_points'):
                if k in data:
                    setattr(self, k, data[k])
            self.talents = [int(clamp(v,0,5)) for v in (self.talents[:6] + [0]*6)[:6]]
            self.skill_points = int(clamp(self.skill_points,0,99))
            self.chapter = int(clamp(self.chapter,0,2))
            self.level = int(clamp(self.level,1,99))
            self.x = clamp(float(self.x),25,WORLD_W-25)
            self.y = clamp(float(self.y),25,WORLD_H-25)
            self.gear = {k:int(clamp(self.gear.get(k,0),0,99)) for k in ('staff','robe','ring')}
            self.bag = [v for v in self.bag[:12] if isinstance(v,dict) and v.get('slot') in self.gear]
            self.hp = clamp(float(self.hp),1,self.max_hp)
            self.mana = clamp(float(self.mana),0,self.max_mana)
            self.random_map()
            # Boss fights restart on load, avoiding unwinnable missing bosses.
            if self.boss_spawned and not self.boss_dead:
                self.boss_spawned = False
            self.overlay = 'story'
            self.paused = True
            self.draw()
        except (OSError, ValueError, TypeError):
            self.say('Сохранение не найдено')

    def say(self, s, t=3):
        self.message, self.message_time = s, t

    def spawn_enemy(self, boss=False):
        angle = random.random()*math.tau
        radius = 380 if boss else random.uniform(310,490)
        x = clamp(self.x + math.cos(angle)*radius, 40, WORLD_W-40)
        y = clamp(self.y + math.sin(angle)*radius, 40, WORLD_H-40)
        hp = (320 + self.chapter*250 + self.level*45) if boss else (52 + self.chapter*23 + self.level*9)
        self.enemies.append(Enemy(x,y,hp,hp, 64 + self.chapter*9 if not boss else 50, 9 + self.chapter*5 if not boss else 21+self.chapter*8, boss))
        if boss:
            self.say('БОСС: '+CHAPTERS[self.chapter]['boss'], 5)

    def next_chapter(self):
        if self.chapter == 2:
            self.finished = True
            self.overlay = 'victory'
            self.paused = True
            self.save()
            return
        self.chapter += 1
        self.kills = 0
        self.boss_spawned = False
        self.boss_dead = False
        self.enemies.clear()
        self.projectiles.clear()
        self.pickups.clear()
        self.x, self.y = WORLD_W/2, WORLD_H/2
        self.hp = self.max_hp
        self.mana = self.max_mana
        self.random_map()
        self.overlay = 'story'
        self.paused = True
        self.save()

    def cast(self, index):
        if self.paused or self.hp <= 0 or self.skill_cd[index] > 0:
            return
        name, cost, cooldown, _ = SPELLS[index]
        if self.mana < cost:
            self.say('Недостаточно маны', 1)
            return
        self.mana -= cost
        self.skill_cd[index] = cooldown * (1-.07*self.talents[5])
        if index == 3:
            self.hp = min(self.max_hp, self.hp + 50 + self.level*7)
            self.say('Исцеление!', 1)
            return
        targets = sorted(self.enemies, key=lambda e:distance((e.x,e.y),(self.x,self.y)))
        if not targets:
            self.say('Поблизости нет врагов', 1)
            self.mana += cost
            self.skill_cd[index] = 0
            return
        if index == 2:
            if distance((targets[0].x,targets[0].y),(self.x,self.y)) >= 450:
                self.mana += cost
                self.skill_cd[index] = 0
                self.say('Враги слишком далеко',1)
                return
            for e in targets[:4]:
                if distance((e.x,e.y),(self.x,self.y)) < 450:
                    self.hit(e, self.damage*1.4*(1+.12*self.talents[2]))
                    self.particles.append([e.x,e.y,0.55,2])
            return
        e = targets[0]
        dx, dy = e.x-self.x, e.y-self.y
        d = max(1, math.hypot(dx,dy))
        self.projectiles.append([self.x,self.y,dx/d*520,dy/d*520,2.0,index])

    def hit(self, enemy, damage):
        enemy.hp -= damage
        if enemy.hp <= 0 and enemy in self.enemies:
            self.enemies.remove(enemy)
            self.gold += random.randrange(3,11)*(self.chapter+1)
            self.xp += 18 + self.chapter*12 + (150 if enemy.boss else 0)
            if enemy.boss:
                self.boss_dead = True
                self.say('Печать получена! Открой портал в центре.', 5)
                self.pickups.append([enemy.x,enemy.y,'seal'])
                self.save()
            else:
                self.kills += 1
                if random.random() < .24:
                    self.pickups.append([enemy.x,enemy.y,'loot'])
            while self.xp >= self.level*85:
                self.xp -= self.level*85
                self.level += 1
                self.skill_points += 1
                self.hp = self.max_hp
                self.mana = self.max_mana
                self.say('НОВЫЙ УРОВЕНЬ: '+str(self.level), 4)

    def loot(self):
        slot = random.choice(['staff','robe','ring'])
        rarity = random.choices(range(4), [62,26,10,2])[0]
        power = max(1, self.chapter+1 + rarity*2 + random.randrange(2))
        names = {'staff':'Посох','robe':'Мантия','ring':'Кольцо'}
        item = {'slot':slot,'power':power,'rarity':rarity,'name':names[slot]+' '+['пепла','луны','костей','бездны'][rarity]}
        if len(self.bag) < 12:
            self.bag.append(item)
            self.say('Добыча: '+item['name'])
        else:
            self.gold += 12
            self.say('Сумка полна: +12 золота')

    def tick(self, dt):
        dt = min(dt, .05)
        if not self.paused:
            self.autosave_timer -= dt
            if self.autosave_timer <= 0:
                self.autosave_timer = 45.0
                self.save(silent=True)
            for i in range(4):
                self.skill_cd[i] = max(0, self.skill_cd[i]-dt)
            self.mana = min(self.max_mana, self.mana+5*dt)
            jx,jy = self.joy
            if jx or jy:
                speed = 205
                self.x = clamp(self.x + jx*speed*dt, 25, WORLD_W-25)
                self.y = clamp(self.y + jy*speed*dt, 25, WORLD_H-25)
            self.spawn_timer -= dt
            if self.spawn_timer <= 0 and len(self.enemies) < 10 and not self.boss_dead:
                if self.kills >= CHAPTERS[self.chapter]['goal']:
                    if not self.boss_spawned:
                        self.spawn_enemy(True)
                        self.boss_spawned = True
                else:
                    self.spawn_enemy()
                self.spawn_timer = 1.9
            for e in self.enemies[:]:
                d = distance((e.x,e.y),(self.x,self.y))
                e.attack_cd -= dt
                e.slow = max(0, e.slow-dt)
                if d > 30:
                    factor = (0.36 if e.slow else 1)*e.speed*dt/max(1,d)
                    e.x += (self.x-e.x)*factor
                    e.y += (self.y-e.y)*factor
                elif e.attack_cd <= 0:
                    self.hp -= max(2,e.damage-self.gear['robe']*1.5)
                    e.attack_cd = 1.1 if not e.boss else .75
                if e.boss:
                    e.shoot_cd -= dt
                    if e.shoot_cd <= 0 and d < 450:
                        self.hp -= max(3, (10+self.chapter*5)-self.gear['robe'])
                        self.particles.append([self.x,self.y,.5,3])
                        e.shoot_cd = 3.0
            for p in self.projectiles[:]:
                p[0] += p[2]*dt
                p[1] += p[3]*dt
                p[4] -= dt
                if p[4] <= 0:
                    self.projectiles.remove(p)
                    continue
                for e in self.enemies[:]:
                    if distance((p[0],p[1]),(e.x,e.y)) < (38 if e.boss else 25):
                        if p[5] == 0:
                            # Fireball explodes and damages nearby enemies.
                            for nearby in self.enemies[:]:
                                if nearby is not e and distance((p[0],p[1]),(nearby.x,nearby.y)) < 95:
                                    self.hit(nearby, self.damage*.75*(1+.15*self.talents[0]))
                        self.hit(e, self.damage*(1.8*(1+.15*self.talents[0]) if p[5] == 0 else 1.15))
                        if p[5] == 1 and e in self.enemies:
                            e.slow = 3 + self.talents[1]*.8
                        self.particles.append([p[0],p[1],.4,p[5]])
                        if p in self.projectiles:
                            self.projectiles.remove(p)
                        break
            for p in self.particles[:]:
                p[2] -= dt
                if p[2] <= 0:
                    self.particles.remove(p)
            for item in self.pickups[:]:
                if distance((self.x,self.y),item[:2]) < 42:
                    if item[2] == 'loot':
                        self.loot()
                    self.pickups.remove(item)
            if self.boss_dead and distance((self.x,self.y),(WORLD_W/2,WORLD_H/2)) < 72:
                self.next_chapter()
            if self.hp <= 0:
                self.hp = 0
                self.paused = True
                self.overlay = 'death'
        if self.message_time > 0:
            self.message_time -= dt
        self.draw()

    def label(self, text, x, y, size=14, color=(1,1,1,1), width=None, bold=False):
        label = Label(text=str(text), font_size=dp(size), color=color, bold=bold,
                      size_hint=(None,None), size=(width or self.width, dp(size*2.0)),
                      pos=(x-(width or self.width)/2,y-dp(size)))
        self.add_widget(label)
        self.labels.append(label)

    def box(self, x,y,w,h,color,r=0):
        Color(*color)
        if r:
            RoundedRectangle(pos=(x,y),size=(w,h),radius=[r])
        else:
            Rectangle(pos=(x,y),size=(w,h))

    def draw(self):
        for label in self.labels:
            self.remove_widget(label)
        self.labels = []
        self.canvas.clear()
        if self.width <= 0 or self.height <= 0:
            return
        w,h = self.width,self.height
        scale = min(w/650,h/820)*1.1
        scale = max(.37,scale)
        cx,cy = w/2,h*.54
        self.action_rects = {}
        with self.canvas:
            self.box(0,0,w,h,(.055,.063,.07,1))
            # World viewport: dark isometric-feeling terrain with procedural ruins.
            for gx in range(-1,12):
                for gy in range(-1,12):
                    wx = math.floor((self.x-600)/130)*130+gx*130
                    wy = math.floor((self.y-600)/130)*130+gy*130
                    sx,sy = cx+(wx-self.x)*scale,cy+(wy-self.y)*scale
                    if -100 < sx < w+100 and -100 < sy < h+100:
                        shade = .10 + ((int(wx/130)*17+int(wy/130)*11)%5)*.008
                        self.box(sx,sy,130*scale+1,130*scale+1,(shade,shade*.97,shade*.83,1))
                        Color(.16,.15,.12,.35)
                        Line(rectangle=(sx,sy,130*scale,130*scale),width=.6)
            # Portal
            px,py = cx+(WORLD_W/2-self.x)*scale,cy+(WORLD_H/2-self.y)*scale
            Color(.32,.15,.6,.85 if self.boss_dead else .2)
            Ellipse(pos=(px-45*scale,py-24*scale),size=(90*scale,48*scale))
            Color(.67,.4,1,1 if self.boss_dead else .24)
            Line(ellipse=(px-45*scale,py-24*scale,90*scale,48*scale),width=3)
            for ox,oy,r in self.obstacles:
                sx,sy = cx+(ox-self.x)*scale,cy+(oy-self.y)*scale
                if -80 < sx < w+80 and -80 < sy < h+80:
                    Color(.24,.23,.22,1)
                    Ellipse(pos=(sx-r*scale,sy-r*.45*scale),size=(r*2*scale,r*.9*scale))
                    self.box(sx-r*.6*scale,sy,r*1.2*scale,r*1.35*scale,(.31,.30,.28,1))
                    self.box(sx-r*.13*scale,sy+r*.15*scale,r*.26*scale,r*.8*scale,(.16,.16,.17,1))
            for item in self.pickups:
                sx,sy=cx+(item[0]-self.x)*scale,cy+(item[1]-self.y)*scale
                Color(*( (.96,.76,.23,1) if item[2]=='loot' else (.7,.3,1,1)))
                Ellipse(pos=(sx-9,sy-9),size=(18,18))
            for e in self.enemies:
                sx,sy=cx+(e.x-self.x)*scale,cy+(e.y-self.y)*scale
                rr=(34 if e.boss else 19)*scale
                Color(.08,.04,.04,.65)
                Ellipse(pos=(sx-rr,sy-rr*.55),size=(rr*2,rr*.8))
                Color(*((.55,.14,.11,1) if e.boss else ((.52,.58,.53,1) if self.chapter<2 else (.63,.32,.23,1))))
                Ellipse(pos=(sx-rr*.75,sy-rr*.4),size=(rr*1.5,rr*1.8))
                Color(.95,.25,.12,1)
                Ellipse(pos=(sx-rr*.4,sy+rr*.45),size=(rr*.23,rr*.2))
                Ellipse(pos=(sx+rr*.2,sy+rr*.45),size=(rr*.23,rr*.2))
                self.box(sx-rr,sy+rr*1.5,rr*2,4,(.27,.06,.06,1))
                self.box(sx-rr,sy+rr*1.5,rr*2*max(0,e.hp/e.maxhp),4,(.83,.2,.14,1))
                if e.boss:
                    self.label(CHAPTERS[self.chapter]['boss'],sx,sy+rr*2.3,12,(1,.68,.5,1),w*.65)
            for p in self.projectiles:
                sx,sy=cx+(p[0]-self.x)*scale,cy+(p[1]-self.y)*scale
                Color(*SPELLS[p[5]][3],1)
                Ellipse(pos=(sx-9,sy-9),size=(18,18))
            for p in self.particles:
                sx,sy=cx+(p[0]-self.x)*scale,cy+(p[1]-self.y)*scale
                Color(*SPELLS[min(p[3],3)][3],min(1,p[2]*2))
                Ellipse(pos=(sx-27,sy-27),size=(54,54))
            # Wizard
            Color(.02,.02,.03,.8)
            Ellipse(pos=(cx-19*scale,cy-13*scale),size=(38*scale,18*scale))
            Color(.20,.15,.31,1)
            Triangle(points=[cx,cy+37*scale,cx-25*scale,cy-25*scale,cx+25*scale,cy-25*scale])
            Color(.45,.32,.64,1)
            Ellipse(pos=(cx-11*scale,cy+7*scale),size=(22*scale,22*scale))
            Color(.77,.68,.91,1)
            Ellipse(pos=(cx-3*scale,cy+14*scale),size=(6*scale,6*scale))
            Color(.56,.4,.24,1)
            Line(points=[cx+18*scale,cy-22*scale,cx+29*scale,cy+39*scale],width=3)
            Color(.45,.78,1,1)
            Ellipse(pos=(cx+22*scale,cy+33*scale),size=(14*scale,14*scale))
            # HUD
            self.box(8,h-75,w-16,67,(.045,.045,.06,.93),10)
            self.box(17,h-34,(w-34)*.60,11,(.28,.08,.09,1),5)
            self.box(17,h-34,(w-34)*.60*max(0,self.hp/self.max_hp),11,(.85,.19,.19,1),5)
            self.box(17,h-51,(w-34)*.60,10,(.07,.13,.3,1),5)
            self.box(17,h-51,(w-34)*.60*max(0,self.mana/self.max_mana),10,(.22,.47,.95,1),5)
            self.label('Ур. %d  •  %d зол.'%(self.level,self.gold),w*.81,h-24,12,(1,.87,.58,1),w*.36,True)
            self.label('Глава %d/3  •  %d/%d'%(self.chapter+1,self.kills,CHAPTERS[self.chapter]['goal']),w*.81,h-46,11,(.8,.82,.85,1),w*.36)
            # Quest text
            self.label(CHAPTERS[self.chapter]['name'],w/2,h-93,15,(.96,.85,.62,1),w*.95,True)
            quest = ('Войди в портал в центре' if self.boss_dead else 'Победи босса' if self.boss_spawned else 'Уничтожь монстров')
            self.label(quest,w/2,h-114,12,(.8,.8,.78,1),w*.9)
            # Joystick touch region
            jx,jy=w*.17,dp(105)
            Color(.55,.58,.65,.24)
            Ellipse(pos=(jx-49,jy-49),size=(98,98))
            Color(.72,.74,.81,.58)
            Ellipse(pos=(jx-23+self.joy[0]*25,jy-23+self.joy[1]*25),size=(46,46))
            # Buttons, accessible even on small screens
            bw=min(dp(62),w*.155)
            gap=dp(7)
            for i,(name,_,_,color) in enumerate(SPELLS):
                bx=w-bw-dp(9)-(i%2)*(bw+gap)
                by=dp(66)+(i//2)*(bw+gap)
                self.action_rects['spell'+str(i)] = (bx,by,bw,bw)
                self.box(bx,by,bw,bw,(.13,.13,.18,.94),12)
                Color(*color,1 if self.skill_cd[i]==0 else .32)
                Ellipse(pos=(bx+bw*.25,by+bw*.35),size=(bw*.5,bw*.5))
                self.label(['ОГОНЬ','ЛЁД','ГРОМ','ЖИЗНЬ'][i],bx+bw*.5,by+dp(10),9,(1,1,1,1),bw)
                if self.skill_cd[i]>0:
                    self.label('%.1f'%self.skill_cd[i],bx+bw*.5,by+bw*.58,12,(1,1,1,1),bw,True)
            self.action_rects['inventory']=(dp(8),dp(9),dp(96),dp(40))
            self.box(dp(8),dp(9),dp(96),dp(40),(.21,.19,.16,1),9)
            self.label('СУМКА',dp(56),dp(29),12,(1,.88,.7,1),dp(96),True)
            self.action_rects['talents']=(dp(111),dp(9),dp(102),dp(40))
            self.box(dp(111),dp(9),dp(102),dp(40),(.17,.21,.27,1),9)
            self.label('ТАЛАНТЫ',dp(162),dp(29),11,(.75,.87,1,1),dp(102),True)
            self.action_rects['pause']=(w-dp(67),h-dp(120),dp(57),dp(36))
            self.box(w-dp(67),h-dp(120),dp(57),dp(36),(.2,.2,.23,1),8)
            self.label('II',w-dp(38),h-dp(102),15,(1,1,1,1),dp(57),True)
            if self.message_time>0:
                self.box(w*.08,h*.73,w*.84,dp(36),(.06,.05,.09,.88),8)
                self.label(self.message,w/2,h*.73+dp(18),12,(1,.87,.62,1),w*.82,True)
            if self.overlay:
                self.draw_overlay(w,h)

    def draw_overlay(self,w,h):
        with self.canvas:
            self.box(0,0,w,h,(.025,.02,.035,.92))
            self.box(w*.06,h*.19,w*.88,h*.62,(.12,.11,.14,1),16)
            self.box(w*.07,h*.2,w*.86,h*.60,(.16,.14,.17,1),13)
            self.action_rects = {}
            if self.overlay == 'menu':
                title='SHADOW ARENA'
                subtitle='ПЕПЕЛ КОЛОКОЛА'
                body='Мрачная ролевая игра\nТри главы • Маг • Монстры • Добыча'
                buttons=[('НОВАЯ ИГРА','new'),('ПРОДОЛЖИТЬ','load')]
            elif self.overlay == 'story':
                title=CHAPTERS[self.chapter]['name']
                subtitle='СЮЖЕТ'
                body=CHAPTERS[self.chapter]['story']
                buttons=[('В БОЙ','resume'),('СОХРАНИТЬ','save')]
            elif self.overlay == 'death':
                title='ТЫ ПОГИБ'
                subtitle='Тьма ещё не победила'
                body='Продолжи с последнего сохранения\nили начни путешествие заново.'
                buttons=[('ЗАГРУЗИТЬ','load'),('ЗАНОВО','new')]
            elif self.overlay == 'victory':
                title='КОЛОКОЛ МОЛЧИТ'
                subtitle='ПОБЕДА!'
                body='Владыка Пепла повержен.\nДеревня спасена.\nТвой путь стал легендой.'
                buttons=[('НОВАЯ ИГРА','new')]
            elif self.overlay == 'talents':
                title='ДРЕВО ТАЛАНТОВ'
                subtitle='Свободных очков: %d'%self.skill_points
                body='Каждый уровень даёт 1 очко. Выбери развитие мага.'
                buttons=[('НАЗАД','resume')]
            elif self.overlay == 'pause':
                title='ПАУЗА'
                subtitle='Пепел ждёт'
                body='Прогресс сохраняется между запусками.\nЗаклинания: огонь, лёд, молния, лечение.'
                buttons=[('ПРОДОЛЖИТЬ','resume'),('СОХРАНИТЬ','save'),('ГЛАВНОЕ МЕНЮ','menu')]
            else:
                title='ИНВЕНТАРЬ'
                subtitle='Нажми на предмет, чтобы надеть'
                body='Посох: +%d  •  Мантия: +%d  •  Кольцо: +%d\nПредметов: %d/12'%(self.gear['staff'],self.gear['robe'],self.gear['ring'],len(self.bag))
                buttons=[('НАЗАД','resume'),('СОХРАНИТЬ','save')]
            self.label(title,w/2,h*.72,clamp(w*.048,16,25),(1,.78,.51,1),w*.82,True)
            self.label(subtitle,w/2,h*.655,13,(.72,.68,.79,1),w*.80,True)
            self.label(body,w/2,h*.555,13,(.92,.9,.86,1),w*.76)
            if self.overlay == 'talents':
                for i,(name,desc,limit) in enumerate(TALENTS):
                    bx=w*.13
                    by=h*.49-i*dp(37)
                    self.action_rects['talent'+str(i)]=(bx,by,w*.74,dp(34))
                    self.box(bx,by,w*.74,dp(33),(.21,.24,.29,1),5)
                    self.label('%s  %d/%d'%(name,self.talents[i],limit),w*.50,by+dp(17),11,(.91,.84,.68,1),w*.7,True)
                start_y=h*.20
            elif self.overlay == 'inventory':
                for i,item in enumerate(self.bag[:8]):
                    bx=w*.13+(i%2)*w*.39
                    by=h*.46-(i//2)*dp(32)
                    self.action_rects['item'+str(i)]=(bx,by,w*.35,dp(30))
                    self.box(bx,by,w*.35,dp(29),(.23,.21,.24,1),5)
                    self.label(item['name']+' +'+str(item['power']),bx+w*.175,by+dp(15),10,(*RARITY[item['rarity']][1],1),w*.34)
                start_y=h*.29
            else:
                start_y=h*.40
            for i,(caption,action) in enumerate(buttons):
                bw=w*.68
                bx=w*.16
                by=start_y-i*dp(51)
                self.action_rects[action]=(bx,by,bw,dp(44))
                self.box(bx,by,bw,dp(44),(.34,.23,.16,1),9)
                self.label(caption,w/2,by+dp(22),13,(1,.93,.83,1),bw,True)

    def on_touch_down(self,touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        x,y=touch.pos
        for action,rect in self.action_rects.items():
            bx,by,bw,bh=rect
            if bx<=x<=bx+bw and by<=y<=by+bh:
                self.action(action)
                return True
        if not self.paused and x<self.width*.44 and y<dp(230):
            self.joy_id=touch.uid
            self.update_joy(x,y)
            return True
        return True

    def on_touch_move(self,touch):
        if touch.uid==self.joy_id:
            self.update_joy(*touch.pos)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self,touch):
        if touch.uid==self.joy_id:
            self.joy_id=None
            self.joy=(0,0)
            return True
        return super().on_touch_up(touch)

    def update_joy(self,x,y):
        dx=x-self.width*.17
        dy=y-dp(105)
        d=max(1,math.hypot(dx,dy))
        m=min(1,d/50)
        self.joy=(dx/d*m,dy/d*m)

    def action(self,a):
        if a.startswith('spell'):
            self.cast(int(a[-1]))
        elif a=='talents':
            self.overlay='talents';self.paused=True;self.joy=(0,0)
        elif a.startswith('talent'):
            i=int(a[6:])
            if self.skill_points>0 and self.talents[i]<TALENTS[i][2]:
                self.skill_points-=1
                self.talents[i]+=1
                self.hp=min(self.hp,self.max_hp)
                self.mana=min(self.mana,self.max_mana)
                self.save(silent=True)
        elif a=='inventory':
            self.overlay='inventory';self.paused=True;self.joy=(0,0)
        elif a=='pause':
            self.overlay='pause';self.paused=True;self.joy=(0,0)
        elif a=='resume':
            self.overlay=None;self.paused=False
        elif a=='new':
            self.start_new();self.overlay='story'
        elif a=='load':
            self.load()
        elif a=='save':
            self.save()
        elif a=='menu':
            self.overlay='menu';self.paused=True
        elif a.startswith('item'):
            i=int(a[4:])
            if i<len(self.bag):
                item=self.bag.pop(i)
                slot=item['slot']
                old=self.gear[slot]
                if item['power']>old:
                    self.gear[slot]=item['power']
                    self.hp=min(self.hp,self.max_hp)
                    self.say('Надето: '+item['name'])
                else:
                    self.gold+=item['power']*5
                    self.say('Продано: +%d золота'%(item['power']*5))
        self.draw()


class ShadowArenaApp(App):
    title='Shadow Arena: Пепел Колокола'
    def build(self):
        Window.clearcolor=(.05,.05,.06,1)
        self.music = SoundLoader.load(os.path.join(os.path.dirname(__file__), 'assets', 'dark_ambient.wav'))
        if self.music:
            self.music.loop = True
            self.music.volume = .35
            self.music.play()
        return Arena()
    def on_pause(self):
        if self.root:
            self.root.save()
        return True
    def on_stop(self):
        if getattr(self, 'music', None):
            self.music.stop()
        if self.root and self.root.hp>0:
            self.root.save()


if __name__=='__main__':
    ShadowArenaApp().run()
