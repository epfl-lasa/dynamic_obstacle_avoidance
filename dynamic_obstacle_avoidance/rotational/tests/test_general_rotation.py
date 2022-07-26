#!/USSR/bin/python3
""" Create the rotation space which is so much needed. ... """
# Author: Lukas Huber
# Github: hubernikus
# Created: 2022-07-07

# Use python 3.10 [annotations / typematching]
from __future__ import annotations  # Not needed from python 3.10 onwards

import copy
import warnings

# import logging
import math
from dataclasses import dataclass

import numpy as np
from numpy import linalg as LA

import networkx as nx

# import igraph

import matplotlib.pyplot as plt
import numpy.typing as npt

from vartools.linalg import get_orthogonal_basis

Vector = npt.ArrayLike
VectorArray = npt.ArrayLike

NodeType = int


def rotate_direction(direction: Vector, base: VectorArray, rotation_angle: float):
    """Returns the rotated of the input vector with respect to the base and rotation angle."""
    # Normalize just to make sure.
    direction = direction / LA.norm(direction)

    dot_prods = np.dot(base.T, direction)
    angle = math.atan2(dot_prods[1], dot_prods[0]) + rotation_angle

    # Convert angle to the two basis-axis
    out_direction = math.cos(angle) * base[:, 0] + math.sin(angle) * base[:, 1]
    out_direction *= math.sqrt(sum(dot_prods**2))

    # Finally, add the orthogonal part (no effect in 2D, but important for higher dimensions)
    out_direction += direction - np.sum(dot_prods * base, axis=1)
    return out_direction


def rotate_array(
    directions: VectorArray,
    base: VectorArray,
    rotation_angle: float,
) -> VectorArray:
    """Rotate upper level base with respect to total."""
    dimension, n_dirs = directions.shape

    directions = directions / LA.norm(directions, axis=0)

    # Matrix dimensions: [2 x n_dirs ] <- [dimension x 2 ].T @ [dimension x n_dirs]
    dot_prods = np.dot(base.T, directions)
    angles = np.arctan2(dot_prods[1, :], dot_prods[0, :]) + rotation_angle

    # Compute output from rotation
    out_vectors = np.tile(base[:, 0], (n_dirs, 1)).T * np.tile(
        np.cos(angles), (dimension, 1)
    ) + np.tile(base[:, 1], (n_dirs, 1)).T * np.tile(np.sin(angles), (dimension, 1))
    out_vectors *= np.tile(np.sqrt(np.sum(dot_prods**2, axis=0)), (dimension, 1))

    # Finally, add the orthogonal part (no effect in 2D, but important for higher dimensions)
    out_vectors += directions - (base @ dot_prods)

    return out_vectors


# Factories
def create_zero_rotation(dimension=3):
    VectorRotationXd(
        base=self._graph.nodes[node_id]["orientation"].base,
        rotation_angle=(
            self._graph.nodes[node_id]["orientation"].rotation_angle
            * self._graph.nodes[node_id]["weight"]
        ),
    )


class VectorRotationTree:
    """
    VectorRotation but originating structured in a tree

    Positive node number reference the corresponding reference-id
    (negative numbers are used for the vectors)
    """

    # TODO: what happens if an obstacle is at angle 'pi'?
    # as it might happend at  zero-level

    def __init__(self, root_id: int, root_direction: Vector) -> None:
        self._graph = nx.DiGraph()
        self._graph.add_node(
            root_id,
            level=0,
            direction=root_direction,
            weight=0,
            orientation=VectorRotationXd(
                base=np.tile(root_direction, (2, 1)).T, rotation_angle=0
            ),
        )

    # def set_root(self, root_id: int, direction: Vector) -> None:
    #     self._graph.add_node(node_id, level=0, direction=direction)

    def add_node(
        self,
        node_id: NodeType,
        direction: Vector,
        parent_id: NodeType,
        rotation_limit: float = math.pi * 0.75,
    ) -> None:

        new_rotation = VectorRotationXd.from_directions(
            self._graph.nodes[parent_id]["direction"],
            direction,
        )

        if rotation_limit and abs(new_rotation.rotation_angle) > rotation_limit:
            rot_factor = (
                2 * math.pi - abs(new_rotation.rotation_angle)
            ) / rotation_limit

            direction = new_rotation.rotate(
                new_rotation.basis[:, 0], rot_factor=rot_factor
            )

            new_rotation.angle = new_rotation.rotation_angle * rot_factor

            warnings.warn(
                f"Rotation is the limit={rotation_limit}. "
                + "Adaptation weight is used. "
            )

        self._graph.add_node(
            node_id,
            level=self._graph.nodes[parent_id]["level"] + 1,
            direction=direction,
            weight=0,
            orientation=new_rotation,
        )

        self._graph.add_edge(
            parent_id,
            node_id,
        )
        # TODO: what happens when you overwrite a node (?)

    def reset_node_weights(self):
        for node_id in self._graph.nodes:
            self._graph.nodes[node_id]["weight"] = 0

    def set_node(self, node_id, parent_id, direction):
        # TODO: implement such that it updates lower and higher nodes (!)
        raise NotImplementedError()

    @property
    def dimension(self):
        try:
            return self._graph.nodes[0]["direction"].shape[0]
        except AttributeError:
            warnings.warn("base or property has not been defined")
            return None

    def get_sorted_nodes(self) -> list(NodeType):
        # level_list = np.zeros(len(self._graph))
        # sorted_list = np.zeros(len(self._graph))
        # for ii, node in enumerate(self._graph):
        # level_list[ii] = self._graph[node]["level"]
        # sorted_list[ii] = node
        # sorted_list = sorted_list[np.argsort(level_list)]

        # node_list = list(self._graph.nodes) #  => somewow this does not work as documented...
        # node_list = [node for node in self._graph.nodes]

        # Ascending sorted node-list
        level_list = [self._graph.nodes[node]["level"] for node in self._graph.nodes]
        node_unsorted = [node for node in self._graph.nodes]
        return [node_unsorted[ii] for ii in np.argsort(level_list)]

    def get_all_childs_children(self, node: NodeType) -> list(NodeType):
        """Returns list of nodes which are in the directional line of the argument node."""
        successor_list = [ii for ii in self._graph.successors(node)]

        ii = 0
        while ii < len(successor_list):
            # Add all children elements to the list
            successor_list += [jj for jj in self._graph.successors(successor_list[ii])]
            ii += 1

        return successor_list

    def get_weighted_mean(self, node_list: list(int), weights: list(float)) -> Vector:
        """Evaluate the weighted mean of the graph."""
        self.reset_node_weights()

        # Weights are stored in the predecessing nodes of the corresponding edge
        for ii, node in enumerate(node_list):
            self._graph.nodes[node]["weight"] = weights[ii]

        # Update cumulated weights
        sorted_list = self.get_sorted_nodes()
        for node_id in sorted_list:
            for succ_id in self._graph.successors(node_id):
                # Where are the weights stored / where are the rotations stored (?)
                self._graph.nodes[succ_id]["weight"] += self._graph.nodes[node_id][
                    "weight"
                ]

        # Create 'partial' orientations
        for node_id in reversed(sorted_list):
            if not "orientation" in self._graph.nodes[node_id]:
                self._graph.nodes[node_id]["part_orientation"] = create_zero_rotation(
                    dimension=3
                )
                continue

            self._graph.nodes[node_id]["part_orientation"] = VectorRotationXd(
                base=self._graph.nodes[node_id]["orientation"].base,
                rotation_angle=(
                    self._graph.nodes[node_id]["orientation"].rotation_angle
                    * self._graph.nodes[node_id]["weight"]
                ),
            )

            if (
                not self._graph.successors(node_id)
                or self._graph.nodes[node_id]["weight"] == 1
            ):
                # No sucessor nodes or full rotation is being kept
                continue

            successors = self.get_all_childs_children(node_id)
            # angles = np.zeros(len(successors))
            # for ii, successor in enumerate(successors):
            #     angles[ii] = successor['orientation'].rotation_angle
            #     basis[:, ii, :] = successor['orientation'].basis

            _succ_basis = [
                self._graph.nodes[succ]["part_orientation"].base for succ in successors
            ]
            if not len(_succ_basis):
                continue

            # Make sure dimension is the first axes for future array restructuring
            succ_basis = np.swapaxes(_succ_basis, 0, 1)

            succ_basis = rotate_array(
                directions=succ_basis.reshape(self.dimension, -1),
                base=self._graph.nodes[node_id]["orientation"].base,
                rotation_angle=(
                    self._graph.nodes[node_id]["orientation"].rotation_angle
                    * (1 - self._graph.nodes[node_id]["weight"])
                ),
            ).reshape(self.dimension, -1, 2)

            for ii, succ in enumerate(successors):
                self._graph.nodes[succ]["part_orientation"].base = succ_basis[:, ii, :]

        return self.evaluate_graph_summing(sorted_list)

    def evaluate_graph_summing(self, sorted_list) -> Vector:
        """Graph summing
        -> this requires $2x (n_{childrend} of node) \forall node \in nodes $
        i.e. does currently not scale well
        But calculations are simple, i.e., this could be sped upt with cython / C++ / Rust
        """
        level_list = [self._graph.nodes[node_id]["level"] for node_id in sorted_list]

        for level in set(level_list):
            # Assumption of shared-basis at each level

            # level_nodes = sorted_list[level_list == level]
            nodelevel_ids = [jj for jj, lev in enumerate(level_list) if lev == level]

            shared_basis = get_orthogonal_basis(
                self._graph.nodes[nodelevel_ids[0]]["part_orientation"].base[:, 0]
            )

            basis2_array = np.array(
                [
                    self._graph.nodes[ii]["part_orientation"].base[:, 1]
                    for ii in nodelevel_ids
                ]
            ).T

            local_basis2 = shared_basis.T @ basis2_array
            local_basis2 *= np.array(
                [
                    self._graph.nodes[jj]["part_orientation"].rotation_angle
                    for jj in nodelevel_ids
                ]
            )
            local_mean_base2 = np.sum(local_basis2, axis=1)

            new_angle = LA.norm(local_mean_base2)
            if new_angle:  # Nonzero
                breakpoint()
                local_mean_base2[0] = 0  # Really (?)
                new_base2 = shared_basis @ (local_mean_base2 / new_angle)
            else:
                # Take random other dimension, i.e., first one
                new_base2 = shared_basis[:, 1]

            all_successors = []
            all_basis = np.zeros((self.dimension, 0))
            for node_id in nodelevel_ids:
                # Transform all child angles to first base-direction
                successors = self.get_all_childs_children(node_id)

                if not successors:
                    # No successors
                    continue

                # Make sure dimension is the first axes for future array restructuring
                _succ_basis = [
                    self._graph.nodes[succ]["part_orientation"].base
                    for succ in successors
                ]
                succ_basis = np.swapaxes(_succ_basis, 0, 1)

                basis = rotate_array(
                    directions=succ_basis.reshape(self.dimension, -1),
                    base=self._graph.nodes[node_id]["part_orientation"].base,
                    rotation_angle=(-1)
                    * self._graph.nodes[node_id]["part_orientation"].rotation_angle,
                )

                all_successors += successors
                all_basis = np.hstack((all_basis, basis))

            if all_successors:
                # Reached the end of the graph - there are no successors anymore
                break

            if not new_angle:
                # Transform to the new base2-direction
                new_base = np.hstack(
                    (level_nodes[0]["part_orientation"].basis[:, 0], new_base2)
                ).T

                succ_basis = rotate_array(
                    directions=succ_basis.reshape(self.dimension, -1),
                    base=new_base,
                    rotation_angle=new_angle,
                ).reshape(self.dimension, -1, 2)

            else:
                # Zero transformation to the new angle
                succ_basis = succ_basis.reshape(self.dimension, -1, 2)

            for ii, node in enumerate(all_successors):
                node["part_orientation"].base = basis[:, ii, :]

        # Return is done outside of the loop for readability
        return new_base2

    def get_rotation_weights(self, parent_id: int, direction: Vector) -> float:
        pass

    def rotate_weighted(self, node_id_list: list(int), weights: list(float)):
        # For safe rotation at the back
        raise NotImplementedError()


class VectorRotationSequence:
    """
    Vector-Rotation environment based on multiple vectors

    Attributes
    ----------
    vectors_array (np.array of shape [dimension x n_rotations + 1]):
        (storing) the inital array of vectors
    basis_array (numpy array of  shape [dimension x n_rotations x 2]):
        contains the basis of all rotations
    rotation_angles: The rotation between going from one to the next basis
    """

    def __init__(self, vectors_array: np.array) -> None:
        # Normalize
        self.vectors_array = vectors_array / LA.norm(vectors_array, axis=0)

        dot_prod = np.sum(
            self.vectors_array[:, 1:] * self.vectors_array[:, :-1], axis=0
        )

        if np.sum(dot_prod == (-1)):  # Any of the values
            raise ValueError("Antiparallel vectors.")

        # Evaluate basis and angles
        vec_perp = self.vectors_array[:, 1:] - self.vectors_array[:, :-1] * dot_prod
        vec_perp = vec_perp / LA.norm(vec_perp, axis=0)

        self.basis_array = np.stack((self.vectors_array[:, :-1], vec_perp), axis=2)
        self.rotation_angles = np.arccos(dot_prod)

    @property
    def n_rotations(self):
        return self.basis_array.shape[1]

    @property
    def dimension(self):
        return self.basis_array.shape[0]

    def base(self) -> Vector:
        return self.basis_array[:, [0, -1]]

    def append(self, direction: Vector) -> None:
        self.basis_array = np.hstack((self.basis_array, direction.reshape(-1, 1)))

        raise NotImplementedError("Finish updating basis and rotation angles.")

    def rotate(self, direction: Vector, rot_factor: float = 1) -> Vector:
        """Rotate over the whole length of the vector."""
        weights = np.zeros(self.n_rotations)
        weights[-1] = rot_factor
        return self.rotate_weighted(direction, weights=weights)

    def rotate_weighted(self, direction: Vector, weights: list[float] = None) -> Vector:
        """
        Returns the rotated direction vector with repsect to the (rotation-)weights

        weights (list of floats (>=0) with length [self.n_rotations]): indicates fraction
        of each rotation which is applied.
        """
        # Starting at the root
        cumulated_weights = np.cumsum(weights[::-1])[::-1]

        if not math.isclose(cumulated_weights[0], 1):
            warnings.warn("Weights are summing up to more than 1.")

        temp_base = np.copy(self.basis_array)
        if weights is None:
            temp_angle = self.rotation_angles

        else:
            temp_angle = self.rotation_angles * cumulated_weights

            # Update the basis of rotation weights from top-to-bottom
            # by rotating upper level base with respect to total
            for ii in reversed(range(self.n_rotations - 1)):
                temp_base[:, (ii + 1) :, :] = rotate_array(
                    directions=temp_base[:, (ii + 1) :, :].reshape(self.dimension, -1),
                    base=temp_base[:, ii, :],
                    rotation_angle=self.rotation_angles[ii]
                    * (1 - cumulated_weights[ii]),
                ).reshape(self.dimension, -1, 2)

        # Finally: rotate from bottom-to-top
        for ii in range(self.n_rotations):
            direction = rotate_direction(
                direction=direction,
                rotation_angle=temp_angle[ii],
                base=temp_base[:, ii, :],
            )
        return direction


@dataclass
class VectorRotationXd:
    """This approach allows successive modulation which can be added up.

    Attributes
    ----------
    base array of size [dimension x 2]: The (orthonormal) base constructed from the to
        input directions
    rotation_angle (float): The rotation angle resulting from the two input directions
    """

    base: VectorArray
    rotation_angle: float

    @classmethod
    def from_directions(cls, vec_init: Vector, vec_rot: Vector) -> VectorRotationXd:
        """Alternative constructor base on two input vectors which define the
        initialization."""

        # # Normalize both vectors
        # vec_init = vec_init / LA.norm(vec_init)
        # vec_rot = vec_rot / LA.norm(vec_rot)

        dot_prod = np.dot(vec_init, vec_rot)
        if dot_prod == (-1):
            raise ValueError("Antiparallel vectors")

        if dot_prod < 1:
            vec_perp = vec_rot - vec_init * dot_prod
            vec_perp = vec_perp / LA.norm(vec_perp)
        else:
            # Zero vector, since rotation never happens
            vec_perp = vec_rot

        return cls(
            base=np.array([vec_init, vec_perp]).T, rotation_angle=np.arccos(dot_prod)
        )

    # @classmethod
    # def zero_rotation(cls, vec_init: Vector) -> VectorRotationXd:
    # return cls(base=np.repeat(vec_init, axis=1), rotation=0)

    @property
    def dimension(self):
        try:
            return self.base.shape[0]
        except AttributeError:
            warnings.warn("base has not been defined")
            return None

    def rotate(self, direction, rot_factor: float = 1):
        """Returns the rotated of the input vector with respect to the base and rotation angle
        rot_factor: factor gives information about extension of rotation"""
        return rotate_direction(
            direction=direction,
            rotation_angle=rot_factor * self.rotation_angle,
            base=self.base,
        )

    def inverse_rotate(self, direction):
        return rotate_direction(
            direction=direction,
            rotation_angle=(-1) * self.rotation_angle,
            base=self.base,
        )


def test_cross_rotation_2d(visualize=False, savefig=False):
    vec0 = np.array([1, 0.3])
    vec1 = np.array([1.0, -1])

    vector_rotation = VectorRotationXd.from_directions(vec0, vec1)

    vec0 /= LA.norm(vec0)
    vec1 /= LA.norm(vec1)
    cross_prod_base = np.cross(vec0, vec1)

    arrow_props = {"head_length": 0.1, "head_width": 0.05}

    vecs_test = [
        [1, -1.2],
        [-1.2, -1],
        [-1.2, 1.3],
    ]

    vecs_rot_list = []
    for ii, vec in enumerate(vecs_test):
        vec_test = np.array(vecs_test[ii])
        vec_test /= LA.norm(vec_test)
        vec_rot = vector_rotation.rotate(vec_test)

        assert np.isclose(
            cross_prod_base, np.cross(vec_test, vec_rot)
        ), "Vectors are not close"

        # For visualization purposes
        vecs_rot_list.append(vec_rot)

    if visualize:
        fig, axs = plt.subplots(2, 2, figsize=(8, 8))

        ax = axs[0, 0]
        vec_1 = vector_rotation.base[:, 0]
        ax.arrow(
            0,
            0,
            vec_1[0],
            vec_1[1],
            color="k",
            **arrow_props,
        )

        vec_perp = vector_rotation.base[:, 1]
        ax.arrow(
            0,
            0,
            vec_perp[0],
            vec_perp[1],
            color="k",
            label="Base",
            **arrow_props,
        )

        ax.arrow(0, 0, vec0[0], vec0[1], color="g", label="Vector 0", **arrow_props)
        ax.arrow(0, 0, vec1[0], vec1[1], color="b", label="Vector 1", **arrow_props)
        ax.legend()

        ax = axs[0, 1]
        axs_test = axs.flatten()[1:]
        for ii, ax in enumerate(axs_test):
            vec_test = vecs_test[ii] / LA.norm(vecs_test[ii])
            ax.arrow(
                0,
                0,
                vec_test[0],
                vec_test[1],
                color="g",
                label="Initial",
                **arrow_props,
            )
            vec_rot = vecs_rot_list[ii]

            ax.arrow(
                0, 0, vec_rot[0], vec_rot[1], color="b", label="Rotated", **arrow_props
            )
            ax.legend()

        for ax in axs.flatten():
            ax.axis("equal")
            ax.set_xlim(-1.1, 1.1)
            ax.set_ylim(-1.1, 1.1)
            ax.grid()
            # ax.legend()

        if savefig:
            figure_name = "rotation_with_perpendicular_basis"
            plt.savefig("figures/" + figure_name + ".png", bbox_inches="tight")


def test_zero_rotation():
    vec_init = np.array([1, 0])
    vec_rot = np.array([1, 0])

    vector_rotation = VectorRotationXd.from_directions(vec_init, vec_rot)

    vec_test = np.array([1, 0])
    vec_rotated = vector_rotation.rotate(vec_test)
    assert np.allclose(vec_test, vec_rotated)

    vec_test = np.array([0, 1])
    vec_rotated = vector_rotation.rotate(vec_test)
    assert np.allclose(vec_test, vec_rotated)


def test_cross_rotation_3d():
    vec_init = np.array([1, 0, 0])
    vec_rot = np.array([0, 1, 0])

    vector_rotation = VectorRotationXd.from_directions(vec_init, vec_rot)

    vec_test = np.array([-1, 0, 0])
    vec_rotated = vector_rotation.rotate(vec_test)
    assert np.allclose(vec_rotated, [0, -1, 0]), "Not correct rotation."

    vec_test = np.array([0, 0, 1])
    vec_rotated = vector_rotation.rotate(vec_test)
    assert np.allclose(vec_rotated, vec_test), "No rotation expected."

    vec_test = np.ones(3)
    vec_test = vec_test / LA.norm(vec_test)
    vec_rotated = vector_rotation.rotate(vec_test)
    assert np.isclose(LA.norm(vec_rotated), 1), "Unit norm expected."


def test_multi_rotation_array():
    # Rotation from 1 to final
    vector_seq = np.array(
        [
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 1],
            [-1, 0, 0],
            [0, -1, 0],
        ]
    ).T

    rotation_seq = VectorRotationSequence(vector_seq)
    rotated_vec = rotation_seq.rotate(direction=np.array([1, 0, 0]))
    assert np.allclose(rotated_vec, [0, -1, 0]), "Unexpected rotation."

    rotation_seq = VectorRotationSequence(vector_seq)
    rotated_vec = rotation_seq.rotate_weighted(
        direction=np.array([1, 0, 0]), weights=np.array([0.5, 0.5, 0, 0])
    )
    out_vec = np.array([0, 1, 1]) / np.sqrt(2)
    assert np.allclose(rotated_vec, out_vec), "Not rotated into second plane."


def test_rotation_tree():
    new_tree = VectorRotationTree(root_id=0, root_direction=np.array([0, 1]))

    new_tree.add_node(node_id=1, direction=np.array([1, 0]), parent_id=0)
    new_tree.add_node(node_id=2, direction=np.array([1, 0]), parent_id=1)

    new_tree.add_node(node_id=3, direction=np.array([-1, 0]), parent_id=0)
    new_tree.add_node(node_id=4, direction=np.array([-1, 0]), parent_id=3)

    weighted_mean = new_tree.get_weighted_mean(
        node_list=[0, 2, 4], weights=[0.3, 0.3, 0.3]
    )
    breakpoint()
    weighted_mean


if (__name__) == "__main__":
    plt.close("all")
    # test_cross_rotation_2d(visualize=True, savefig=0)
    # test_zero_rotation()
    # test_cross_rotation_3d()
    # test_multi_rotation_array()

    # test_rotation_tree()
    test_rotation_tree()

    print("\nDone with tests.")
