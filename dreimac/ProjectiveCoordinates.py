import numpy as np 
import numpy.linalg as linalg
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.pyplot as plt 
from ripser import Rips
import time
import warnings
from CSMSSMTools import getSSM, getGreedyPermDM, getGreedyPermEuclidean, get_greedy_perm
from TDAUtils import add_cocycles

def PPCA(class_map, proj_dim, verbose = False):
    """
    Principal Projective Component Analysis (Jose Perea 2017)
    
    Parameters
    ----------
    class_map : ndarray (N, d)
        For all N points of the dataset, membership weights to
        d different classes are the coordinates
    proj_dim : integer
        The dimension of the projective space onto which to project
    verbose : boolean
        Whether to print information during iterations
    """
    if verbose:
        print("Doing PPCA on %i points in %i dimensions down to %i dimensions"%\
                (class_map.shape[0], class_map.shape[1], proj_dim))
    X = class_map.T
    variance = np.zeros(X.shape[0]-1)

    n_dim = class_map.shape[1]
    tic = time.time()
    # Projective dimensionality reduction : Main Loop
    XRet = None
    for i in range(n_dim-1):
        # Project onto an "equator"
        _, U = linalg.eigh(X.dot(X.T))
        U = np.fliplr(U)
        variance[-i-1] = np.mean((np.pi/2-np.real(np.arccos(np.abs(U[:, -1][None, :].dot(X)))))**2)
        Y = (U.T).dot(X)
        y = np.array(Y[-1, :])
        Y = Y[0:-1, :]
        X = Y/np.sqrt(1-np.abs(y)**2)[None, :]
        if i == n_dim-proj_dim-2:
            XRet = np.array(X)
    if verbose:
        print("Elapsed time PPCA: %.3g"%(time.time()-tic))
    #Return the variance and the projective coordinates
    return {'variance':variance, 'X':XRet.T}


def ProjCoords(P, n_landmarks, distance_matrix = False, perc = 0.99, \
                maxdim = 1, cocycle_idx = [0], proj_dim = 3, verbose = False):
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
    maxdim : int
        Maximum dimension of homology.  Only dimension 1 (mod 2) is needed for 
        projective coordinates, but it may be of interest to see other 
        dimensions on the subsampled point set (e.g. for a Klein bottle)
    cocycle_idx : list
        Add the cocycles together, sorted from most to least persistent
    proj_dim : integer
        Dimension down to which to project the data
    verbose : boolean
        Whether to print detailed information during the computation
    """
    n_data = P.shape[0]
    rips = Rips(coeff=2, maxdim=maxdim, do_cocycles=True)
    
    # Step 1: Compute greedy permutation
    tic = time.time()
    if distance_matrix:
        res = getGreedyPermDM(P, n_landmarks, verbose)
        perm, dist_land_data = res['perm'], res['DLandmarks']
        dist_land_land = P[perm, :]
        dist_land_land = dist_land_land[:, perm]
    else:    
        #res = getGreedyPermEuclidean(P, n_landmarks, verbose)
        #Y, dist_land_data, perm = res['Y'], res['D'], res['perm']
        perm, _, dist_land_data = get_greedy_perm(P, n_landmarks)
        Y = P[perm, :]
        dist_land_land = getSSM(Y)
        
    if verbose:
        print("Elapsed time greedy permutation: %.3g seconds"%(time.time() - tic))



    # Step 2: Compute H1 with cocycles on the landmarks
    tic = time.time()
    dgms = rips.fit_transform(dist_land_land, distance_matrix=True)
    dgm1 = dgms[1]
    
    dgm1 = dgm1/2.0 #Need so that Cech is included in rips
    if verbose:
        print("Elapsed time persistence: %.3g seconds"%(time.time() - tic))
    idx_p1 = np.argsort(dgm1[:, 0] - dgm1[:, 1])
    cocycle = rips.cocycles_[1][idx_p1[cocycle_idx[0]]]
    cohomdeath = -np.inf
    cohombirth = np.inf
    cocycle = np.zeros((0, 3))
    for k in range(len(cocycle_idx)):
        cocycle = add_cocycles(cocycle, rips.cocycles_[1][idx_p1[cocycle_idx[k]]])
        cohomdeath = max(cohomdeath, dgm1[idx_p1[cocycle_idx[k]], 0])
        cohombirth = min(cohombirth, dgm1[idx_p1[cocycle_idx[k]], 1])

    # Step 3: Determine radius for balls ( = interpolant btw data coverage and cohomological birth)
    coverage = np.max(np.min(dist_land_data, 1))
    r_cover = (1-perc)*max(cohomdeath, coverage) + perc*cohombirth
    if verbose:
        print("r_cover = %.3g"%r_cover)
    

    # Step 4: Create the open covering U = {U_1,..., U_{s+1}} and partition of unity

    # Let U_j be the set of data points whose distance to l_j is less than
    # r_cover
    U = dist_land_data < r_cover
    # Compute subordinated partition of unity varphi_1,...,varphi_{s+1}
    # Compute the bump phi_j(b) on each data point b in U_j. phi_j = 0 outside U_j.
    phi = np.zeros_like(dist_land_data)
    phi[U] = r_cover - dist_land_data[U]

    # Compute the partition of unity varphi_j(b) = phi_j(b)/(phi_1(b) + ... + phi_{s+1}(b))
    varphi = phi / np.sum(phi, 0)[None, :]

    # To each data point, associate the index of the first open set it belongs to
    ball_indx = np.argmax(U, 0)

    # Step 5: From U_1 to U_{s+1} - (U_1 \cup ... \cup U_s), apply classifying map

    # compute all transition functions
    cocycle_matrix = np.ones((n_landmarks, n_landmarks))
    cocycle_matrix[cocycle[:, 0], cocycle[:, 1]] = -1
    cocycle_matrix[cocycle[:, 1], cocycle[:, 0]] = -1
    class_map = np.sqrt(varphi.T)
    for i in range(n_data):
        class_map[i, :] *= cocycle_matrix[ball_indx[i], :]
    
    res = PPCA(class_map, proj_dim, verbose)
    res["cocycle"] = cocycle[:, 0:2]
    res["dist_land_land"] = dist_land_land
    res["dist_land_data"] = dist_land_data
    res["dgm1"] = dgm1*2
    res["idx_p1"] = idx_p1
    res["rips"] = rips
    res["perm"] = perm
    return res

def rotmat(a, b = np.array([])):
    """
    Construct a d x d rotation matrix that rotates
    a vector a so that it coincides with a vector b

    Parameters
    ----------
    a : ndarray (d)
        A d-dimensional vector that should be rotated to b
    b : ndarray(d)
        A d-dimensional vector that shoudl end up residing at 
        the north pole (0,0,...,0,1)
    """
    if (len(a.shape) > 1 and np.min(a.shape) > 1)\
         or (len(b.shape) > 1 and np.min(b.shape) > 1):
        print("Error: a and b need to be 1D vectors")
        return None
    a = a.flatten()
    a = a/np.sqrt(np.sum(a**2))
    d = a.size

    if b.size == 0:
        b = np.zeros(d)
        b[-1] = 1
    b = b/np.sqrt(np.sum(b**2))
    
    c = a - np.sum(b*a)*b
    # If a numerically coincides with b, don't rotate at all
    if np.sqrt(np.sum(c**2)) < 1e-15:
        return np.eye(d)

    # Otherwise, compute rotation matrix
    c = c/np.sqrt(np.sum(c**2))
    lam = np.sum(b*a)
    beta = np.sqrt(1 - np.abs(lam)**2)
    rot = np.eye(d) - (1-lam)*(c[:, None].dot(c[None, :])) \
                    - (1-lam)*(b[:, None].dot(b[None, :])) \
                    + beta*(b[:, None].dot(c[None, :]) - c[:, None].dot(b[None, :]))
    return rot


def getStereoProjCodim1(pX, randomSeed = -1):
    from sklearn.decomposition import PCA
    X = pX.T
    # Put points all on the same hemisphere
    if randomSeed >= 0:
        np.random.seed(randomSeed)
        u = np.random.randn(3)
        u = u/np.sqrt(np.sum(u**2))
    else:
        _, U = linalg.eigh(X.dot(X.T))
        u = U[:, 0]
    XX = rotmat(u).dot(X)
    ind = XX[-1, :] < 0
    XX[:, ind] *= -1
    # Do stereographic projection
    S = XX[0:-1, :]/(1+XX[-1, :])[None, :]
    return S.T

def plotRP2Stereo(S, f, arrowcolor = 'c', facecolor = (0.15, 0.15, 0.15)):
    """
    Plot a 2D Stereographic Projection

    Parameters
    ----------
    S : ndarray (N, 2)
        An Nx2 array of N points to plot on RP2
    f : ndarray (N) or ndarray (N, 3)
        A function with which to color the points, or a list of colors
    """
    if not (S.shape[1] == 2):
        warnings.warn("Plotting stereographic RP2 projection, but points are not 2 dimensional")
    if f.size > S.shape[0]:
        plt.scatter(S[:, 0], S[:, 1], 20, c=f, cmap='afmhot')
    else:
        plt.scatter(S[:, 0], S[:, 1], 20, f, cmap='afmhot')
    t = np.linspace(0, 2*np.pi, 200)
    plt.plot(np.cos(t), np.sin(t), c=arrowcolor)
    plt.axis('equal')
    ax = plt.gca()
    
    ax.arrow(-0.1, 1, 0.001, 0, head_width = 0.15, head_length = 0.2, fc = arrowcolor, ec = arrowcolor, width = 0)
    ax.arrow(0.1, -1, -0.001, 0, head_width = 0.15, head_length = 0.2, fc = arrowcolor, ec = arrowcolor, width = 0)
    ax.set_facecolor(facecolor)

def plotRP3Stereo(ax, S, f, draw_sphere = False):
    """
    Plot a 3D Stereographic Projection

    Parameters
    ----------
    ax : matplotlib axis
        3D subplotting axis
    S : ndarray (N, 3)
        An Nx3 array of N points to plot on RP3
    f : ndarray (N) or ndarray (N, 3)
        A function with which to color the points, or a list of colors
    draw_sphere : boolean
        Whether to draw the 2-sphere
    """
    if not (S.shape[1] == 3):
        warnings.warn("Plotting stereographic RP3 projection, but points are not 4 dimensional")
    if f.size > S.shape[0]:
        ax.scatter(S[:, 0], S[:, 1], S[:, 2], c=f, cmap='afmhot')
    else:
        c = plt.get_cmap('afmhot')
        C = f - np.min(f)
        C = C/np.max(C)
        C = c(np.array(np.round(C*255), dtype=np.int32))
        C = C[:, 0:3]
        ax.scatter(S[:, 0], S[:, 1], S[:, 2], c=C, cmap='afmhot')
    if draw_sphere:
        u, v = np.mgrid[0:2*np.pi:20j, 0:np.pi:20j]
        ax.set_aspect('equal')    
        x = np.cos(u)*np.sin(v)
        y = np.sin(u)*np.sin(v)
        z = np.cos(v)
        ax.plot_wireframe(x, y, z, color="k")

def testProjCoordsRP2(NSamples, NLandmarks):
    np.random.seed(NSamples)
    X = np.random.randn(NSamples, 3)
    X = X/np.sqrt(np.sum(X**2, 1))[:, None]

    SOrig = getStereoProjCodim1(X)
    phi = np.sqrt(np.sum(SOrig**2, 1))
    theta = np.arccos(np.abs(SOrig[:, 0]))

    D = X.dot(X.T)
    D = np.abs(D)
    D[D > 1.0] = 1.0
    D = np.arccos(D)
    
    res = ProjCoords(D, NLandmarks, proj_dim=2, distance_matrix=True, verbose=True)
    variance, X = res['variance'], res['X']
    varcumu = np.cumsum(variance)
    varcumu = varcumu/varcumu[-1]

    plt.subplot(231)
    res["rips"].plot(show=False)
    plt.title("%i Points, %i Landmarks"%(NSamples, NLandmarks))
    plt.subplot(234)
    plt.plot(varcumu)
    plt.scatter(np.arange(len(varcumu)), varcumu)
    plt.xlabel("Dimension")
    plt.ylabel("Cumulative Variance")
    plt.title("Cumulative Variance")

    SFinal = getStereoProjCodim1(X)
    plt.subplot(232)
    plotRP2Stereo(SOrig, phi)
    plt.title("Ground Truth $\\phi$")
    plt.subplot(233)
    plotRP2Stereo(SFinal, phi)
    plt.title("Projective Coordinates $\\phi$")

    plt.subplot(235)
    plotRP2Stereo(SOrig, theta)
    plt.title("Ground Truth $\\theta$")
    plt.subplot(236)
    plotRP2Stereo(SFinal, theta)
    plt.title("Projective Coordinates $\\theta$")

    plt.show()

def testProjCoordsKleinBottle(res, NLandmarks):
    """
    Test projective coordinates on the Klein bottle

    Parameters
    ----------
    res : int
        Resolution along each axis.  Total number of points will be res*res
    NLandmarks : int
        Number of landmarks to take in the projective coordinates computation
    """
    theta = np.linspace(0, 2*np.pi, res)
    theta, phi = np.meshgrid(theta, theta)
    theta = theta.flatten()
    phi = phi.flatten()
    NSamples = theta.size
    R = 2
    r = 1
    X = np.zeros((NSamples, 4))
    X[:, 0] = (R + r*np.cos(theta))*np.cos(phi)
    X[:, 1] = (R + r*np.cos(theta))*np.sin(phi)
    X[:, 2] = r*np.sin(theta)*np.cos(phi/2)
    X[:, 3] = r*np.sin(theta)*np.sin(phi/2)

    res = ProjCoords(X, NLandmarks, cocycle_idx = [0, 1], \
                    proj_dim=3, distance_matrix=False, verbose=True)
    variance, X = res['variance'], res['X']
    varcumu = np.cumsum(variance)
    varcumu = varcumu/varcumu[-1]
    dgm1 = res["dgm1"]

    fig = plt.figure()
    plt.subplot(221)
    res["rips"].plot(show=False)

    plt.title("%i Points, %i Landmarks"%(NSamples, NLandmarks))
    plt.subplot(222)
    plt.plot(varcumu)
    plt.scatter(np.arange(len(varcumu)), varcumu)
    plt.xlabel("Dimension")
    plt.ylabel("Cumulative Variance")
    plt.title("Cumulative Variance")

    SFinal = getStereoProjCodim1(X)
    
    #plotRP2Stereo(SFinal, theta)
    ax = fig.add_subplot(223, projection='3d')
    plotRP3Stereo(ax, SFinal, theta)
    plt.title("$\\theta$")
    ax = fig.add_subplot(224, projection='3d')
    plotRP3Stereo(ax, SFinal, phi)
    plt.title("$\\phi$")

    plt.show()

if __name__ == '__main__':
    testProjCoordsRP2(10000, 60)
    #testProjCoordsKleinBottle(100, 100)
