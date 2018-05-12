import numpy as np 
import numpy.linalg as linalg
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.pyplot as plt 
from ripser import Rips
import time

def getCSM(X, Y):
    """
    Return the Euclidean cross-similarity matrix between the M points
    in the Mxd matrix X and the N points in the Nxd matrix Y.
    
    Parameters
    ----------
    X : ndarray (M, d)
        A matrix holding the coordinates of M points
    Y : ndarray (N, d) 
        A matrix holding the coordinates of N points
    Return
    ------
    D : ndarray (M, N)
        An MxN Euclidean cross-similarity matrix
    """
    C = np.sum(X**2, 1)[:, None] + np.sum(Y**2, 1)[None, :] - 2*X.dot(Y.T)
    C[C < 0] = 0
    return np.sqrt(C)

def getGreedyPermEuclidean(X, M, verbose = False):
    """
    A Naive O(NM) algorithm to do furthest points sampling, assuming
    the input is a Euclidean point cloud.  This saves computation
    over having compute the full distance matrix if the number of
    landmarks M << N
    
    Parameters
    ----------
    X : ndarray (N, d) 
        An Nxd Euclidean point cloud
    M : integer
        Number of landmarks to compute
    verbose: boolean
        Whether to print progress

    Return
    ------
    result: Dictionary
        {'Y': An Mxd array of landmarks, 
         'perm': An array of indices into X of the greedy permutation
         'lambdas': Insertion radii of the landmarks
         'D': An MxN array of distances from landmarks to points in X}
    """
    # By default, takes the first point in the permutation to be the
    # first point in the point cloud, but could be random
    N = X.shape[0]
    perm = np.zeros(M, dtype=np.int64)
    lambdas = np.zeros(M)
    ds = getCSM(X[0, :][None, :], X).flatten()
    D = np.zeros((M, N))
    D[0, :] = ds
    for i in range(1, M):
        idx = np.argmax(ds)
        perm[i] = idx
        lambdas[i] = ds[idx]
        thisds = getCSM(X[idx, :][None, :], X).flatten()
        D[i, :] = thisds
        ds = np.minimum(ds, thisds)
        if verbose:
            interval = int(0.05*M)
            if i%interval == 0:
                print("Greedy perm %i%s done..."%(int(100.0*i/float(M)), "%"))
    Y = X[perm, :]
    return {'Y':Y, 'perm':perm, 'lambdas':lambdas, 'D':D}

def getGreedyPermDM(D, M, verbose = False):
    """
    A Naive O(NM) algorithm to do furthest points sampling, assuming
    the input is a N x N distance matrix
    
    Parameters
    ----------
    D : ndarray (N, N) 
        An N x N distance matrix
    M : integer
        Number of landmarks to compute
    verbose: boolean
        Whether to print progress

    Return
    ------
    result: Dictionary
        {'perm': An array of indices into X of the greedy permutation
         'lambdas': Insertion radii of the landmarks
         'DLandmarks': An MxN array of distances from landmarks to points in the point cloud}
    """
    # By default, takes the first point in the permutation to be the
    # first point in the point cloud, but could be random
    N = D.shape[0]
    perm = np.zeros(M, dtype=np.int64)
    lambdas = np.zeros(M)
    ds = D[0, :]
    for i in range(1, M):
        idx = np.argmax(ds)
        perm[i] = idx
        lambdas[i] = ds[idx]
        ds = np.minimum(ds, D[idx, :])
        if verbose:
            interval = int(0.05*M)
            if i%interval == 0:
                print("Greedy perm %i%s done..."%(int(100.0*i/float(M)), "%"))
    DLandmarks = D[perm, :] 
    return {'perm':perm, 'lambdas':lambdas, 'DLandmarks':DLandmarks}

def PPCA(class_map, proj_dim, verbose = False):
    """
    Principal Projective Component Analysis
    
    Parameters
    ----------
    class_map : ndarray (N, d)
        For all N points of the dataset, membership weights to
        d different classes are the coordinates
    proj_dim : integer
        The dimension to which to reduce the coordinates
    verbose : boolean
        Whether to print information during iterations
    """
    if verbose:
        print("Doing PPCA on %i points in %i dimensions down to %i dimensions"%\
                (class_map.shape[0], class_map.shape[1], proj_dim))
    X = class_map.T
    variance = np.zeros(X.shape[0]-1)

    n_dim = class_map.shape[1]
    n_iter = n_dim-proj_dim-1
    tic = time.time()
    # Projective dimensionality reduction : Main Loop
    for i in range(n_iter):
        if verbose:
            interval = int(0.05*n_dim)
            if i%interval == 0:
                print("Projective coordinates %i%s done..."%(int(100.0*i/float(n_dim)), "%"))  
        # Project onto an "equator"
        w, U = linalg.eigh(X.dot(X.T))
        U = np.fliplr(U)
        variance[-i-1] = np.mean((np.pi/2-np.real(np.arccos( np.abs(U[:, -1][None, :].dot(X)))))**2)
        Y = (U.T).dot(X)
        y = np.array(Y[-1, :])
        Y = Y[0:-1, :]
        X = Y/np.sqrt(1-np.abs(y)**2)[None, :]

    # Projective dimensionality reduction : Coordinates Loop
    Z = np.array(X)
    for j in range(proj_dim):
        if verbose:
            interval = int(0.05*n_dim)
            if i%interval == 0:
                print("Projective coordinates %i%s done..."%(int(100.0*i/float(n_dim)), "%"))  
        # Project onto an "equator"
        w, U = linalg.eigh(Z.dot(Z.T))
        U = np.fliplr(U)
        variance[proj_dim-j-1] = np.mean((np.pi/2-np.real(np.arccos(np.abs(U[:, -1][None, :].dot(Z)))))**2)
        Y = (U.T).dot(Z)
        y = np.array(Y[-1, :])
        Y = Y[0:-1, :]
        Z = Y/np.sqrt(1-np.abs(y)**2)[None, :]
    if verbose:
        print("Elapsed time PPCA: %.3g"%(time.time() - tic))
    return {'variance':variance, 'X':X, 'Z':Z}

def ProjCoords(P, n_landmarks, distance_matrix = False, perc = 0.99, \
                proj_dim = 3, verbose = False):
    """
    Perform multiscale projective coordinates via persistent cohomology of 
    sparse filtrations (Jose Perea 2018)
    Parameters
    ----------
    P : ndarray (n_data, d)
        n_data x d array of points
    n_landmarks : integer
        Number of landmarks to sample
    distance_matrix : boolean
        If true, then X is a distance matrix, not a Euclidean point cloud
    perc : float
        Percent coverage
    proj_dim : integer
        Dimension down to which to project the data
    verbose : boolean
        Whether to print detailed information during the computation
    """
    n_data = P.shape[0]
    rips = Rips(coeff=2, maxdim=1, do_cocycles=True)
    
    # Step 1: Compute greedy permutation
    tic = time.time()
    if distance_matrix:
        res = getGreedyPermDM(P, n_landmarks, verbose)
        perm, dist_land_data = res['perm'], res['DLandmarks']
        dist_land_land = P[perm, :]
        dist_land_land = dist_land_land[:, perm]
    else:    
        res = getGreedyPermEuclidean(P, n_landmarks, verbose)
        Y, dist_land_data = res['Y'], res['D']
        dist_land_land = getCSM(Y, Y)
    if verbose:
        print("Elapsed time greedy permutation: %.3g seconds"%(time.time() - tic))

    # Step 2: Compute H1 with cocycles on the landmarks
    tic = time.time()
    dgms = rips.fit_transform(dist_land_land, distance_matrix=True)
    if verbose:
        print("Elapsed time persistence: %.3g seconds"%(time.time() - tic))
    dgm1 = dgms[1]
    idx_mp1 = np.argmax(dgm1[:, 1] - dgm1[:, 0])
    cocycle = rips.cocycles_[1][idx_mp1]

    # Step 3: Determine radius for balls ( = interpolant btw data coverage and cohomological birth)
    coverage = np.max(np.min(dist_land_data, 1))
    r_birth = (1-perc)*max(dgm1[idx_mp1, 0], coverage) + perc*dgm1[idx_mp1, 1]

    # Step 4: Create the open covering U = {U_1,..., U_{s+1}} and partition of unity

    # Let U_j be the set of data points whose distance to l_j is less than
    # r_birth
    U = dist_land_data < r_birth
    # Compute subordinated partition of unity varphi_1,...,varphi_{s+1}
    # Compute the bump phi_j(b) on each data point b in U_j. phi_j = 0 outside U_j.
    phi = np.zeros_like(dist_land_data)
    phi[U] = r_birth - dist_land_data[U]

    # Compute the partition of unity varphi_j(b) = phi_j(b)/(phi_1(b) + ... + phi_{s+1}(b))
    varphi = phi / np.sum(phi, 0)[None, :]

    # To each data point, associate the index of the first open set it belongs to
    indx = np.argmax(U, 0)


    # Step 5: From U_1 to U_{s+1} - (U_1 \cup ... \cup U_s), apply classifying map

    # compute all transition functions
    cocycle_matrix = np.ones((n_landmarks, n_landmarks))
    cocycle_matrix[cocycle[:, 0], cocycle[:, 1]] = -1
    cocycle_matrix[cocycle[:, 1], cocycle[:, 0]] = -1
    class_map = np.sqrt(varphi.T)
    for i in range(n_data):
        class_map[i, :] *= cocycle_matrix[indx[i], :]
    
    res = PPCA(class_map, proj_dim, verbose)
    variance, X, Z = res['variance'], res['X'], res['Z']

    plt.plot(variance)
    plt.show()
    

def testGreedyPermEuclidean():
    t = np.linspace(0, 2*np.pi, 10000)
    X = np.zeros((len(t), 2))
    X[:, 0] = np.cos(t)
    X[:, 1] = np.sin(t)
    res = getGreedyPermEuclidean(X, 50, True)
    Y, D = res['Y'], res['D']
    plt.subplot(121)
    plt.scatter(X[:, 0], X[:, 1], 10)
    plt.scatter(Y[:, 0], Y[:, 1], 40)
    plt.subplot(122)
    plt.imshow(D, aspect = 'auto')
    plt.show()

def testProjCoordsRP2():
    phi = np.linspace(0, 2*np.pi, 100)
    theta = np.linspace(0, np.pi, 100)
    phi, theta = np.meshgrid(phi, theta)
    phi = phi.flatten()
    theta = theta.flatten()
    N = len(phi)
    X = np.zeros((N, 3))
    X[:, 0] = np.cos(phi)*np.cos(theta)
    X[:, 1] = np.cos(phi)*np.sin(theta)
    X[:, 2] = np.sin(phi)
    
    """
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    ax.scatter(X[:, 0], X[:, 1], X[:, 2])
    plt.show()
    """
    D = X.dot(X.T)
    D = np.abs(D)
    D[D > 1.0] = 1.0
    D = np.arccos(D)
    
    ProjCoords(D, 100, True, verbose=True)

if __name__ == '__main__':
    #testGreedyPermEuclidean()
    testProjCoordsRP2()