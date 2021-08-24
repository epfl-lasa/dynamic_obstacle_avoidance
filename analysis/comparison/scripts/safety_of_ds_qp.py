"""
Replicating the paper of
'Safety of Dynamical Systems With MultipleNon-Convex Unsafe Sets UsingControl Barrier Functions'
"""
from dataclasses import dataclass
from typing import Callable

import numpy as np
from numpy import linalg as LA

import matplotlib.pyplot as plt
from matplotlib import cm

from vartools.dynamical_systems import DynamicalSystem, LinearSystem
from vartools.dynamical_systems import plot_dynamical_system_streamplot
from vartools.math import get_numerical_gradient, get_numerical_hessian
from vartools.math import get_numerical_hessian_fast
from vartools.math import get_scaled_orthogonal_projection

from vartools.states import ObjectPose

from dynamic_obstacle_avoidance.obstacles import Obstacle, Sphere
from dynamic_obstacle_avoidance.containers import BaseContainer

from barrier_functions import BarrierFunction, CirclularBarrier, DoubleBlobBarrier
from _base_qp import ControllerQP

# from cvxopt.modeling import variable
from cvxopt import solvers, matrix

class StarshapeTransformContainer(BaseContainer):
    """
    Obstacle space transformation & optimization according to:
    'Safety of Dynamical Systems With MultipleNon-Convex
    Unsafe Sets UsingControl Barrier Functions'
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Use navigation container for trasnformations
        self.navigation_container = NavigationContainer()
        self.navigation_container._obstacle_list = self._obstacle_list
        
    # def add(self):
        # pass

    @property
    def dimension(self):
        return self._obstacle_list[0].dimension

    def diffeomorphism_transformation(self, position, lambda_value=1000):
        return self.navigation_container.transform_to_sphereworld(position)
    
    def transform_obstacles_to_sphere_world(self):
        """ Default sphere world assumption. """
        # return self._obstacle_list

        # TODO: -> update trafo function
        self.initial_sphere_world_list = self._obstacle_list
        self.sphere_world_list = self._obstacle_list

    def get_position_in_sphere_world(self, position):
        """ Default sphere world assumption. """
        return position

    def get_velocity_in_sphere_world(self, velocity):
        """ Default sphere world assumption. """
        return velocity

    @property
    def it_boundary(self):
        # What iteration is boundary
        return 0

    def update(self, position, velocity, delta_time=0.01):
        """ Closed Loop QP-solved update of position & velocity. """
        dim = self.dimension
        n_obs = len(self.sphere_world_list)
        optimal_control = self.get_optimal_displacement(position, velocity)
        
        for ii in range(len(self.sphere_world_list)-1):
            obs = self.sphere_world_list[ii]
            
            obs.position = obs.position + optimal_control[ii*dim:(ii+1)*dim] * delta_time
            obs.radius = obs.radius + optimal_control[ii*n_obs+ii] * delta_time

        # And for the boundary
        self.sphere_world_list[-1].radius = (self.sphere_world_list[-1].radius
                                             + optimal_control[-1]*delta_time)

    def get_optimal_displacement(self, position, velocity, kappa=1, K_p=1):
        """
        Control law:
        
        Attributes
        ----------
        q: state 'x'x mapped into sphere-world i.e. q = F(x)
        q_i: state 'x' of obstacle 'i' mapped in the sphere-world
        ρ_i: radius of obstacle 'i' mappend in the sphere-world
        """
        # Create QP-solver of the form
        # min ( 1/2 x.T P x + q.T x ) 
        # s.t 
        #     A x < b
        #
        # sol = solver.qp(P, q, A, b)
        # self.sphere_world_list = self.get_obstacles_in_sphere_world()
        dim = self.dimension

        q_i = []
        r_i = []
        for obs in self.sphere_world_list:
            if obs.is_boundary:
                r_0 = obs.radius
                q_0 = obs.position
            else:
                q_i.append(obs.position)
                r_i.append(obs.radius)
        
        qq = self.get_position_in_sphere_world(position)
        q_dot = self.get_velocity_in_sphere_world(velocity)

        n_obs_plus_boundary = len(self.sphere_world_list)
        n_obs = n_obs_plus_boundary - 1
        
        # Length of vectors u_{p,i} & u_{q,i}
        n_variables = n_obs*self.dimension + n_obs_plus_boundary

        # CBF (C1) -- Keeping q away from boundary
        # A_C1 = np.zeros((n_obs_plus_boundary, n_variables))
        A_C1_q = np.zeros((n_obs_plus_boundary, n_obs*self.dimension))
        A_C1_r = np.zeros((n_obs_plus_boundary, n_obs_plus_boundary))
        b_C1 = np.zeros(n_obs_plus_boundary)
        for ii in range(n_obs):
            A_C1_q[ii, dim*ii:dim*(ii+1)] = (-2)*(q_i[ii]-qq)
            A_C1_r[ii, ii] = 2*r_i[ii]
            b_C1[ii] = (-2*(q_i[ii]-qq).dot(q_dot)
                        + self.gamma_function(self.h_i(qq, q_i[ii], r_i[ii])))

        # Special case for boundary
        A_C1_r[-1, -1] = (-2)*r_0
        b_C1[-1] = (2*(q_0 - qq).dot(q_dot)
                    + self.gamma_function(self.h_0(qq, q_0, r_0)))

        A_C1 = np.hstack((A_C1_q, A_C1_r))

        # CBF (C2) -- No collision between obstacles
        A_C2_q = np.zeros((n_obs*n_obs-n_obs, n_obs*self.dimension))
        A_C2_r = np.zeros((A_C2_q.shape[0], n_obs_plus_boundary))
        b_C2 = np.zeros(A_C2_q.shape[0])

        it = 0
        for ii in range(n_obs):
            for jj in range(n_obs):
                if ii == jj:
                    continue
                
                breakpoint() # Just checking htat it works in zaa future..
                A_C2_q[it, ii*dim:(ii+1)*dim] = -2*(q_i[ii] - q_i[jj])
                A_C2_q[it, jj*dim:(jj+1)*dim] =  2*(q_i[ii] - q_i[jj])
                A_C2_r[it, ii] = 2*(r_i[ii] + r_i[jj])
                A_C2_r[it, jj] = 2*(r_i[ii] + r_i[jj])
                b_C2[it] = self.gamma(self.h_ij(q_i[ii], q_j[jj], r_i[ii], r_j[jj]))
                it += 1 # Least errorprone iterator
                
        A_C2 = np.hstack((A_C2_q, A_C2_r))

        # CBF (C3) -- No collision with hull
        A_C3_q = np.zeros((n_obs, n_obs*self.dimension))
        A_C3_r = np.zeros((A_C3_q.shape[0], n_obs_plus_boundary))
        b_C3 = np.zeros(A_C3_q.shape[0])
        for ii in range(n_obs):
            A_C3_q[ii, ii*dim:(ii+1)*dim] = 2*(q_i[ii] - q_0)
            A_C3_r[ii, ii] = 2*(r_0 - r_i[ii])
            
            # Special for boundary
            A_C3_r[ii, -1] = (-2)*(r_0 - r_i[ii])

        A_C3 = np.hstack((A_C3_q, A_C3_r))

        AA = np.vstack((A_C1, A_C2, A_C3))
        bb = np.hstack((b_C1, b_C2, b_C3))

        PP = np.diag((np.hstack((np.ones(n_obs*dim),
                                 kappa*np.ones(n_obs_plus_boundary) )) ))

        # Nominal Control
        u_q_i = []
        u_r_i = []
        it = 0
        for obs in self.initial_sphere_world_list:
            if obs.is_boundary:
                u_r_0 = obs.radius - r_0 
            else:
                u_q_i.append(obs.position - q_i[ii])
                u_r_i.append(obs.radius - r_i[ii])
                it += 1 # easiest itcount

        qq = np.hstack((K_p*(-2)*np.array(u_q_i).flatten(),
                        kappa*K_p*(-2)*np.array(u_r_i),
                        kappa*K_p*(-2)*u_r_0)).astype(float)
        
        # sol = solvers.qp(P=matrix(PP), q=matrix(qq).T, G=matrix(AA), h=matrix(bb).T)
        sol = solvers.qp(P=matrix(PP), q=matrix(qq), G=matrix(AA), h=matrix(bb))
        return np.array(sol['x']).flatten()

    def h_0(self, q, q_0, r_0):
        return r_0**2 - LA.norm(q_0 - q)**2

    def h_i(self, q, q_i, r_i):
        return LA.norm(q_i - q)**2 - r_i**2

    def h_ij(self, q_i, q_j, r_i, r_j):
        return LA.norm(q_i - q_j)**2 - (r_i + r_j)**2
    
    def gamma_function(self, value):
        return value


class ClosedLoopQP(ControllerQP):
    """
    System of the form:

    dot x = f_x * x + g_x * u

    with a controller to avoid the barrier function h(x)
    
    Properties
    ----------
    f_x
    g_x
    barrier_function
    
    """
    def __init__(self, f_x, g_x, barrier_function: Obstacle):
        self.f_x = f_x
        self.g_x = g_x
        self.barrier_function = barrier_function

    # def set_control(self, control):
        # self._control = control

    def get_optimal_control(self, position):
        gradient = self.barrier_function.evaluate_gradient(position)

        # Lie derivative of h: L_f h(x) / L_g h(x)
        lie_of_h_wrt_f = gradient.dot(self.evaluate_base_dynamics(position))
        lie_of_h_wrt_g = gradient.dot(self.evaluate_control_dynamics(position))

        gamma_of_h = self.extended_class_function(
            self.barrier_function.get_barrier_value(position))

        # Create QP-solver of the form
        # min ( 1/2 x.T P x + q.T x ) 
        # s.t G x < h
        #     A x = b
        #
        # sol = solver.qp(P, q, G, h)
        # sol = solver.qp(P, q, G, h, A, b)
        PP = matrix([[1.0]])
        qq = matrix([0.0])

        GG = (-1)*matrix([lie_of_h_wrt_g])
        hh = matrix([[lie_of_h_wrt_f + gamma_of_h]])
        
        sol = solvers.qp(PP, qq, GG, hh)
        return sol['x']

    def extended_class_function(self, barrier_function_value):
        """ Not described in paper - assumption of zero value. 'lambda'-function """
        return barrier_function_value
    
    def evaluate_with_control(self, position, control):
        """ Controller acts on internal dynamics. """
        return self.f_x.evaluate(position) + self.g_x.evaluate(position)*control
    

def plot_integrate_trajectory(delta_time=0.005, n_steps=1000):
    # start_position = [-4, 4]
    # start_position = [4, 4]
    x_lim = [-5, 5]
    y_lim = [-2, 6.5]

    dimension = 2


    f_x = LinearSystem(
        A_matrix=np.array([[-6, 0],
                           [0, -1]])
        )
    g_x = LinearSystem(A_matrix=np.eye(dimension))

    # barrier_function = DoubleBlobBarrier(
        # blob_matrix=np.array([[10.0, 0.0],
                              # [0.0, -1.0]]),
        # center_position=np.array([0.0, 3.0]))

    barrier_function = CirclularBarrier(
        radius=1.0,
        center_position=np.array([0, 3]),
        )

    dynamics = ClosedLoopQP(f_x=f_x, g_x=g_x, barrier_function=barrier_function)

    start_position_list = [
        [4, 4],
        [-4, 4] 
        ]
    
    fig, ax = plt.subplots(figsize=(7.5, 6))

    for start_position in start_position_list:
        position = np.zeros((dimension, n_steps+1))
        position[:, 0] = start_position
        for ii in range(n_steps):
            vel = dynamics.evaluate(position[:, ii])
            position[:, ii+1] = position[:, ii] + vel*delta_time
            
        ax.plot(position[0, :], position[1, :])
    # ax.plot(barrier_function.center_position[0], barrier_function.center_position[1], 'k*')
    
    ax.plot(0, 0, 'k*')
    ax.set_aspect('equal', adjustable='box')
    ax.set_xlim(x_lim)
    ax.set_ylim(y_lim)
    ax.grid()
    
    
def plot_main_vector_field():
    dimension = 2
    f_x = LinearSystem(
        A_matrix=np.array([[-6, 0],
                           [0, -1]])
        )
    g_x = LinearSystem(A_matrix=np.eye(dimension))

    # closed_loop_ds = ClosedLoopQP(f_x=f_x, g_x=g_x)
    # closed_loop_ds.evaluate_with_control(position, control)

    plot_dynamical_system_streamplot(
        dynamical_system=f_x, x_lim=[-10, 10], y_lim=[-10, 10])


def plot_barrier_function():
    fig, ax = plt.subplots(figsize=(7.5, 6))
    
    x_lim = [-5, 5]
    y_lim = [-2, 6]

    n_grid = 100
    
    x_vals, y_vals = np.meshgrid(np.linspace(x_lim[0], x_lim[1], n_grid),
                                 np.linspace(y_lim[0], y_lim[1], n_grid),
                                 )
    
    positions = np.vstack((x_vals.reshape(1, -1), y_vals.reshape(1, -1)))
    values = np.zeros(positions.shape[1])

    barrier_function = DoubleBlobBarrier(
        blob_matrix=np.array([[10, 0],
                              [0, -1]]),
        center_position=np.array([0, 3]))

    barrier_function = CirclularBarrier(
        radius=1.0,
        center_position=np.array([0, 3])
        )
    
    for ii in range(positions.shape[1]):
        values[ii] = barrier_function.get_barrier_value(positions[:, ii])

    cs = ax.contourf(positions[0, :].reshape(n_grid, n_grid),
                    positions[1, :].reshape(n_grid, n_grid),
                    values.reshape(n_grid, n_grid),
                    np.linspace(-10.0, 0.0, 11),
                    # np.linspace(-10.0, 0.0, 2),
                    # vmin=-0.1, vmax=0.1,
                    # np.linspace(-10, 10.0, 101),
                    # cmap=cm.YlGnBu,
                    # linewidth=0.2, edgecolors='k'
                    )
    
    cbar = fig.colorbar(cs,
                        # ticks=np.linspace(-10, 0, 11)
                        )

    plt.grid()
    ax.set_aspect('equal', adjustable='box')


def plot_spherial_dynamic_container():
    """ Plot surrounding in different actions. """
    x_lim = [-4, 4]
    y_lim = [-4, 6]
    
    sphere_world = StarshapeTransformContainer()
    
    sphere_world.append(
        Sphere(
        center_position=np.array([1, 1]),
        radius=0.4,
        ))

    sphere_world.append(
        Sphere(
        center_position=np.array([0, 0]),
        radius=3,
        is_boundary=True,
        ))

    sphere_world.transform_obstacles_to_sphere_world()

    pos = np.array([0.5, 0.5])
    vel = np.array([0, 0])

    fig, ax = plt.subplots(figsize=(7.5, 6))
    plt.plot(pos[0], pos[1], 'bo')

    for ii in range(len(sphere_world)):
        obs = sphere_world.sphere_world_list[ii]
        obs.draw_obstacle()
        boundary_points = obs.boundary_points_global
        plt.plot(boundary_points[0, :], boundary_points[1, :], 'k')
        plt.plot(obs.center_position[0], obs.center_position[1], 'k+')
    
    sphere_world.update(position=pos, velocity=vel)

    for ii in range(len(sphere_world)):
        obs = sphere_world.sphere_world_list[ii]
        obs.draw_obstacle()
        boundary_points = obs.boundary_points_global
        plt.plot(boundary_points[0, :], boundary_points[1, :], 'g')
        plt.plot(obs.center_position[0], obs.center_position[1], 'g+')

    ax.set_aspect('equal', adjustable='box')
    ax.set_xlim(x_lim)
    ax.set_ylim(y_lim)
    

if (__name__) == "__main__":
    plt.ion()
    solvers.options['show_progress'] = False
    # plot_main_vector_field()
    
    # plot_barrier_function()
    # plot_integrate_trajectory()
    
    plot_spherial_dynamic_container()

    plt.show()
