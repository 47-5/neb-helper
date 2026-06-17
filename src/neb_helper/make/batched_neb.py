from __future__ import annotations

import numpy as np
from ase.mep.neb import NEB, NEBState, Precon, PreconImages, minimize_rotation_and_translation


class BatchedNEB(NEB):
    """ASE NEB variant that evaluates all image energies/forces in one MLFF batch."""

    def __init__(self, *args, force_evaluator, **kwargs):
        super().__init__(*args, **kwargs)
        self.force_evaluator = force_evaluator

    def get_forces(self):
        images = self.images

        if self.remove_rotation_and_translation:
            for i in range(1, self.nimages):
                minimize_rotation_and_translation(images[i - 1], images[i])

        evaluation = self.force_evaluator.evaluate(images)
        energies = np.asarray(evaluation.energies, dtype=float).reshape(self.nimages)
        all_forces = np.asarray(evaluation.forces, dtype=float).reshape(
            self.nimages, self.natoms, 3
        )
        self._apply_image_constraints(all_forces)
        forces = all_forces[1:-1].copy()

        if self.precon is None or isinstance(self.precon, (str, Precon, list)):
            self.precon = PreconImages(self.precon, images)

        precon_forces = self.precon.apply(forces, index=slice(1, -1))
        self.energies = energies
        self.real_forces = np.zeros((self.nimages, self.natoms, 3))
        self.real_forces[1:-1] = forces

        state = NEBState(self, images, energies)
        self.imax = state.imax
        self.emax = state.emax

        spring1 = state.spring(0)
        self.residuals = []
        for i in range(1, self.nimages - 1):
            spring2 = state.spring(i)
            tangent = self.neb_method.get_tangent(state, spring1, spring2, i)
            tangential_force = np.vdot(forces[i - 1], tangent)
            imgforce = precon_forces[i - 1]

            if i == self.imax and self.climb:
                if self.method == "aseneb":
                    tangent_mag = np.vdot(tangent, tangent)
                    imgforce -= 2 * tangential_force / tangent_mag * tangent
                else:
                    imgforce -= 2 * tangential_force * tangent
            else:
                self.neb_method.add_image_force(
                    state, tangential_force, tangent, imgforce, spring1, spring2, i
                )
                residual = self.precon.get_residual(i, imgforce)
                self.residuals.append(residual)

            spring1 = spring2

        return precon_forces.reshape((-1, 3))

    def _apply_image_constraints(self, all_forces) -> None:
        for image, forces in zip(self.images, all_forces):
            for constraint in image.constraints:
                if hasattr(constraint, "adjust_forces"):
                    constraint.adjust_forces(image, forces)
