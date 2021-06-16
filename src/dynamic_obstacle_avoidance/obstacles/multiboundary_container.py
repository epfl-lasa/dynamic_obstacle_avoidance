""" Container for Obstacle to treat the intersction (and exiting) between different walls. """
# Author: Lukas Huber 
# Mail hubernikus@gmail.com
# License: BSD (c) 2021

import warnings
import numpy as np

from dynamic_obstacle_avoidance.obstacles import BaseContainer

from vartools.dynamicalsys.closedform import evaluate_linear_dynamical_system


class MultiBoundaryContainer(BaseContainer):
    """ Container to treat multiple boundaries / walls."""
    def __init__(self, obs_list=None, *args, **kwargs):
        super().__init__(obs_list=obs_list, *args, **kwargs)

        if obs_list is not None:
            raise NotImplementedError()
        
        else:
            self._parent_array = np.zeros(0, dtype=int)
            self._children_list = []
            self._parent_intersection_point = []

        self._attractractor_position = None

    def append(self, value, parent=None):
        """ Add new obstacle & adapting container-properties"""
        super().append(value)
        self._parent_array = np.hstack((self._parent_array, [-1]))
        self._children_list.append([])
        self._parent_intersection_point.append(None)

        if parent is not None:
            # Automatically define graph
            if parent == -1:
                self.extend_graph(child=self.n_obstacles-1, parent=self.n_obstacles-2)

    def __delitem__(self, key):
        super().append(value)
        breakpoint() # Test if it was executed correctly
        del self._children_list[key]
        self._parent_array = np.delete(self._parent_array, key)
        
        del self._parent_intersection_point[key]
        
    def get_parent(self, it):
        """ Returns parent (int) of the Node [it] as input (int) """
        return self._parent_array[it]

    def get_children(self, it):
        return self._children_list[it]

    def extend_graph(self, child, parent):
        """ Use internal functions to update parents & children."""
        self.set_parent(it=child, parent=parent)
        self.add_children(it=parent, children=[child])
        
    def set_parent(self, it, parent):
        self._parent_array[it] = parent
    
    def add_children(self, it, children):
        if isinstance(children, int):
            children = [children]
        self._children_list[it] = self._children_list[it] + children

    def get_intersection(self, it_obs1, it_obs2):
        """Get the intersection betweeen two obstacles contained in the list.
        The intersection is numerically based on the drawn points. """
        self[it_obs1].create_shape()
        self[it_obs2].create_shape()
        intersect = self[it_obs1].shape.intersection(self[it_obs2].shape)
        intersections = np.array(intersect.exterior.coords.xy)
        intersection = np.mean(intersections, axis=1)
        
        return intersection
    
    def get_boundary_list(self):
        """Returns obstacle list containing all boundary-elements. """
        # TODO MAYBE: store boundaries in separate list (?)
        return [self[ii] for ii in range(self.n_obstacles) if self[ii].is_boubndary]

    def get_boundary_ind(self):
        """ Returns indeces of the current container which are equivalent to obstacles."""
        return np.array([self[ii].is_boundary for ii in range(self.n_obstacles)])

    # def update_convergence_attractor_tree(self):
    def update_intersection_graph(self, attractor_position=None):
        """Caclulate the intersection with each of the children. """
        for ii in range(self.n_obstacles):
            if self.get_parent(ii) < 0: # Root element
                self._parent_intersection_point[ii] = None
            else:
                self._parent_intersection_point[ii] = self.get_intersection(
                    it_obs1=ii, it_obs2=self.get_parent(ii))

        self._attractor_position = attractor_position
        
    def check_collision(self, position):
        """Returns collision with environment (type Bool)
        Note that obstacles are mutually additive, i.e. no collision with any obstacle
        while the boundaries are mutually subractive, i.e. collision free with at least one boundary
        """
        gamma_list_boundary = []
        
        for oo in range(self.n_obstacles):
            gamma = self[oo].get_gamma(position, in_global_frame=True)

            if self[oo].is_boundary:
                gamma_list_boundary.append(gamma)
                
            elif gamma < 1:
                # Collided with an obstacle
                return True
            
        # No collision with any obstacle so far
        return all(np.array(gamma_list_boundary) <= 1)

    def check_collision_array(self, positions):
        """ Return array of checked collisions of type bool. """
        collision_array = np.zeros(positions.shape[1], dtype=bool)
        for it in range(positions.shape[1]):
            collision_array[it] = self.check_collision(positions[:, it])
        return collision_array
        
    def update_relative_reference_point(self, position, gamma_margin_close_wall=1e-6):
        """ Get the local reference point as described in active-learning.
        !!! Current assumption: all obstacles are wall. """

        ind_boundary = self.get_boundary_ind()
        gamma_list = np.zeros(self.n_obstacles)
        for ii in range(self.n_obstacles):
            gamma_list[ii] = self[ii].get_gamma(position, in_global_frame=True,
                                                relative_gamma=False)
        
        ind_inside = np.logical_and(gamma_list > 1, ind_boundary)
        ind_close = np.logical_and(gamma_list > gamma_margin_close_wall, ind_boundary)
        
        num_close = np.sum(ind_close)
            
        for ii, ii_self in zip(range(np.sum(ind_inside)), np.arange(self.n_obstacles)[ind_inside]):
            # Displacement_weight for each obstacle
            # TODO: make sure following function is for obstacles other than ellipses (!)
            boundary_point = self[ii_self].get_intersection_with_surface(
                direction=(position - self[ii_self].center_position), in_global_frame=True)

            weights = np.zeros(num_close)
            
            dist_boundary_point = np.linalg.norm(boundary_point-self[ii_self].center_position)
            dist_point = np.linalg.norm(position-self[ii_self].center_position)
            
            for jj, jj_self in zip(range(num_close), np.arange(self.n_obstacles)[ind_close]):
                if ii_self == jj_self:
                    continue
                gamma_boundary_point = self[jj_self].get_gamma(
                    boundary_point, in_global_frame=True, relative_gamma=False)
                if gamma_boundary_point < 1:
                    # Only obstacles are considered which intersect at the (projected) boundar point
                    continue

                # Weight for the distance to the surface
                weight_1 = (dist_point)/(dist_boundary_point-dist_point)
                # Weight for importance of the corresponding boundary
                weight_2 = gamma_boundary_point - 1

                weights[jj] = 1-1 / (1 + weight_1*weight_2)

            rel_reference_weight = np.max(weights)

            if rel_reference_weight > 1:
                # TODO: remove aftr debugging..
                breakpoint()
                raise ValueError("Weight greater than 1...")

            self[ii_self].global_relative_reference_point = (
                rel_reference_weight*position +
                (1 - rel_reference_weight)*self[ii_self].global_reference_point)

            dist_rel_ref = np.linalg.norm(self[ii_self].global_relative_reference_point
                                          - self[ii_self].center_position)
            relative_gamma = (dist_boundary_point-dist_rel_ref)/(dist_point-dist_rel_ref)

            self[ii_self].set_relative_gamma_at_position(
                position=position, relative_gamma=relative_gamma)
            
        for ii_self in np.arange(self.n_obstacles)[~ind_inside]:
            self[ii_self].reset_relative_reference()
    
    def get_convergence_direction(self, position, it_obs, attractor_position=None):
        """ Get the (null) direction for a specific obstacle in the multi-body-boundary
        container which serves for the rotational-modulation. """
        # breakpoint()
        if attractor_position is not None:
            self._attractor_position = attractor_position
        # Project point on surface
        if self._parent_intersection_point[it_obs] is None:
            if self._attractor_position is None:
                raise ValueError("Need 'attractor_position' to evaluate the desired direction.")
            local_attractor = self._attractor_position
        else:
            local_attractor = self[it_obs].get_intersection_with_surface(
                direction=(self._parent_intersection_point[it_obs]-self[it_obs].center_position),
                in_global_frame=True)

        direction = evaluate_linear_dynamical_system(
            position=position, center_position=local_attractor)

        # Really needed (redundant I believe)
        dir_mag = np.linalg.norm(direction)
        if dir_mag: # nonzero
            direction = direction / dir_mag
        return direction

    def plot_convergence_attractor(self, ax, attractor_position):
        """ Plot the local-graph for all obstacles """
        for ii in range(self.n_obstacles):
            if self.get_parent(ii) < 0:   # is the root
                ax.plot([attractor_position[0], self[ii].position[0]],
                         [attractor_position[1], self[ii].position[1]],
                         '-', color='#808080')
                ax.plot(attractor_position[0], attractor_position[1], 'k*')
            else:
                local_attractor = self._parent_intersection_point[ii]
                
                ax.plot([local_attractor[0], self[ii].position[0]],
                         [local_attractor[1], self[ii].position[1]],
                         '-', color='#808080')
                ax.plot(local_attractor[0], local_attractor[1], 'k*')

                ii_parent = self.get_parent(ii)

                ax.plot([local_attractor[0], self[ii_parent].position[0]],
                         [local_attractor[1], self[ii_parent].position[1]],
                         '-', color='#808080')
            ax.plot(self[ii].position[0], self[ii].position[1], 'k+')