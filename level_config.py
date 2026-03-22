"""Level config — Level N = N AI opponents, escalating difficulty and arena shape."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Set, Tuple


class ArenaShape(Enum):
    FULL="full"; L_SHAPE="l_shape"; CROSS="cross"
    RING="ring"; BRIDGES="bridges"; ISLANDS="islands"


def build_active_set(shape: ArenaShape, grid_w: int, grid_h: int) -> Set[Tuple[int,int]]:
    cells: Set[Tuple[int,int]] = set()
    cx, cy = grid_w//2, grid_h//2
    if shape == ArenaShape.FULL:
        for x in range(grid_w):
            for y in range(grid_h): cells.add((x,y))
    elif shape == ArenaShape.L_SHAPE:
        for x in range(grid_w):
            for y in range(grid_h):
                if not (x>=cx and y<=cy): cells.add((x,y))
    elif shape == ArenaShape.CROSS:
        bw=max(2,grid_w//3); bh=max(2,grid_h//3)
        for x in range(grid_w):
            for y in range(grid_h):
                if (cy-bh//2<=y<=cy+bh//2) or (cx-bw//2<=x<=cx+bw//2): cells.add((x,y))
    elif shape == ArenaShape.RING:
        outer_r=min(cx,cy)-1; inner_r=max(1,outer_r-2)
        for x in range(grid_w):
            for y in range(grid_h):
                d=math.hypot(x-cx,y-cy)
                if inner_r<=d<=outer_r: cells.add((x,y))
    elif shape == ArenaShape.BRIDGES:
        for x in range(grid_w):
            for row_y in [cy-3,cy,cy+3]:
                for off in (0,1):
                    ty=row_y+off
                    if 0<=ty<grid_h: cells.add((x,ty))
    elif shape == ArenaShape.ISLANDS:
        for ox,oy in [(cx//2,cy//2),(cx+cx//2,cy//2),(cx//2,cy+cy//2),(cx+cx//2,cy+cy//2)]:
            for dx in range(-2,3):
                for dy in range(-2,3):
                    tx,ty=ox+dx,oy+dy
                    if 0<=tx<grid_w and 0<=ty<grid_h: cells.add((tx,ty))
    return cells


@dataclass
class TileDifficulty:
    grace_period:float=3.0; base_interval:float=3.0; min_interval:float=0.8
    scale_rate:float=0.95; base_simultaneous:int=1; max_simultaneous:int=4
    sim_ramp_times:list=field(default_factory=lambda:[30,60,90])
    warning_duration:float=1.5; target_player:bool=False

@dataclass
class AIProfile:
    count:int=1; speed_multiplier:float=1.0; decision_interval:float=0.22
    lookahead:float=42.0; chase_weight:float=0.0; sabotage_radius:float=0.0
    use_power:bool=False; power_use_interval:float=15.0; power_count:int=1

@dataclass
class HazardProfile:
    start_delay:float=15.0; bullet_interval:float=3.0; bullet_min_interval:float=1.0
    bullet_speed:float=300.0; trap_interval:float=8.0; trap_min_interval:float=4.0
    trap_speed:float=150.0; max_traps:int=4; difficulty_scale_rate:float=0.98

@dataclass
class OrbConfig:
    max_orbs:int=3; spawn_interval:float=8.0

@dataclass
class LevelConfig:
    number:int; name:str; description:str; arena_shape:ArenaShape
    tile:TileDifficulty; ai:AIProfile; hazard:HazardProfile; orb:OrbConfig
    bg_tint:Tuple[int,int,int,int]=(0,0,0,0); score_bonus:int=100


LEVELS: list[LevelConfig] = [
    LevelConfig(1,"Training Grounds","1 opponent, full arena. Learn the ropes.",
        ArenaShape.FULL,
        TileDifficulty(5.0,4.0,1.5,0.97,1,2,[45,90],2.0),
        AIProfile(1,0.80,0.30,40.0,0.0,0.0,False,99,1),
        HazardProfile(25.0,4.0,2.0,220.0,14.0,8.0,90.0,1,0.98),
        OrbConfig(3,9.0),(15,35,5,20),100),
    LevelConfig(2,"Floating Islands","2 opponents. L-shape — corners go first.",
        ArenaShape.L_SHAPE,
        TileDifficulty(4.0,3.2,1.2,0.96,1,3,[35,70],1.8),
        AIProfile(2,0.90,0.26,45.0,0.10,0.0,False,99,1),
        HazardProfile(20.0,3.5,1.5,260.0,11.0,6.0,110.0,2,0.98),
        OrbConfig(3,8.0),(30,20,0,18),200),
    LevelConfig(3,"Crumbling Bridges","3 opponents. Cross shape — hold the center.",
        ArenaShape.CROSS,
        TileDifficulty(3.5,2.8,1.0,0.95,2,4,[30,60],1.5),
        AIProfile(3,1.00,0.22,50.0,0.20,0.0,True,14.0,2),
        HazardProfile(15.0,3.0,1.2,290.0,9.0,5.0,130.0,3,0.98),
        OrbConfig(4,7.0),(40,10,10,22),350),
    LevelConfig(4,"Shattered Platform","4 opponents. Ring arena — void center awaits.",
        ArenaShape.RING,
        TileDifficulty(3.0,2.4,0.9,0.94,2,4,[25,50],1.3,True),
        AIProfile(4,1.05,0.20,55.0,0.30,80.0,True,12.0,2),
        HazardProfile(12.0,2.5,1.0,310.0,7.0,4.0,150.0,4,0.98),
        OrbConfig(4,6.5),(60,10,0,30),550),
    LevelConfig(5,"The Last Stand","5 opponents. Narrow bridges — no safe corners.",
        ArenaShape.BRIDGES,
        TileDifficulty(2.5,2.0,0.8,0.93,2,5,[20,40],1.2,True),
        AIProfile(5,1.10,0.18,60.0,0.55,70.0,True,10.0,3),
        HazardProfile(10.0,2.0,0.8,340.0,6.0,3.5,170.0,5,0.98),
        OrbConfig(5,5.5),(10,0,50,38),800),
    LevelConfig(6,"Chaos Realm","6 opponents. Scattered islands — every step a gamble.",
        ArenaShape.ISLANDS,
        TileDifficulty(2.0,1.6,0.6,0.92,3,6,[15,30],1.1,True),
        AIProfile(6,1.15,0.16,65.0,0.70,90.0,True,9.0,3),
        HazardProfile(8.0,1.7,0.65,360.0,5.0,3.0,190.0,5,0.98),
        OrbConfig(5,5.0),(20,0,60,45),1100),
    LevelConfig(7,"Nightmare","7 predators. Pure survival.",
        ArenaShape.FULL,
        TileDifficulty(1.5,1.2,0.5,0.91,3,6,[12,25],1.0,True),
        AIProfile(7,1.25,0.14,70.0,0.85,100.0,True,8.0,3),
        HazardProfile(6.0,1.4,0.5,390.0,4.0,3.0,210.0,6,0.98),
        OrbConfig(6,4.5),(30,0,60,55),1500),
]
MAX_LEVEL = len(LEVELS)

def get_level(number:int)->LevelConfig:
    return LEVELS[max(0,min(number-1,len(LEVELS)-1))]