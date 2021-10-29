#!/USSR/bin/python3
"""
Vector fields of different setups
"""
# Author: LukasHuber
# Email: lukas.huber@epfl.ch
# Created:  2021-09-23
import time
from math import pi

import numpy as np
import matplotlib.pyplot as plt

from dynamic_obstacle_avoidance.obstacles import Polygon, Cuboid, Ellipse, Cross
from dynamic_obstacle_avoidance.containers import ObstacleContainer

from dynamic_obstacle_avoidance.visualization import plot_obstacles

from dynamic_obstacle_avoidance.visualization.vector_field_visualization import (
    Simulation_vectorFields
)


from vartools.dynamical_systems import LinearSystem


def multiple_cross_vectorfiel():
    environment = ObstacleContainer()

    environment.append(Cross(
        center_position=np.array([-1.0, -1.0])
        ))

    environment.append(Cross(
        center_position=np.array([1.0, -1.0])
        ))

    environment.append(Cross(
        center_position=np.array([1.0, 1.0])
        ))

    environment.append(Cross(
        center_position=np.array([-1.0, 1.0])
        ))

    fig, ax = plt.subplots()
    plot_obstacles(ax=ax, obs=environment, x_range=[-5, 5], y_range=[-5, 5])

    plt.grid('show')


if (__name__) == "__main__":
    plt.close('all')
    plt.ion()
    
    multiple_cross_vectorfiel()
