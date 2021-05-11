import numpy as np
import matplotlib.pyplot as plt

def gamma_field_visualization(x_lim, y_lim, obstacle, grid_number=30, dim=2):
    ''' Draw the gamma of one obstacle. '''

    x_vals = np.linspace(x_lim[0], x_lim[1], grid_number)
    y_vals = np.linspace(y_lim[0], y_lim[1], grid_number)

    gamma_values = np.zeros((grid_number, grid_number))
    positions = np.zeros((dim, grid_number, grid_number))

    for ix in range(grid_number):
        for iy in range(grid_number):
            positions[:, ix, iy] = [x_vals[ix], y_vals[iy]]
            
            gamma_values[ix, iy] = obstacle.get_gamma(positions[:, ix, iy], in_global_frame=True)


    fig = plt.figure(figsize=(10, 8))
    cs = plt.contourf(positions[0, :, :], positions[1, :, :],  gamma_values, 
                      np.arange(1.0, 2.0, 0.1),
                      extend='max', alpha=0.6, zorder=-3)

    cbar = fig.colorbar(cs)
