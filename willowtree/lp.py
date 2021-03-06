def lp(z, q, k, tol = 1e-9, extra_precision = False):
    '''
    Generate a time-inhomogeneous, discrete time Markov chain for the willow
    tree [1] via linear programming (LP), using the discrete density pairs
    {z(i), q(i)}, for i = 1, ..., n, output of the function 'sampling'.

    The willow tree linear programming problem is:

                                      c'x                           (1)
                         subject to:
                                      A_eq * x = b_eq               (2)
                                      p(k; i,j) >= 0                (3)

    with:

     * c: the vector of coefficients of the linear objective function;
     * A_eq: a matrix of linear equality constraints;
     * b_eq: a vector of linear equality constraints;
     * p(k; i,j): transition probability at position (i,j) in the k-th
                  transition matrix;
     * x: the array solution to the problem.

    Each solution x, when reshaped, is a transition matrix P(k), for k = 1,
    ..., n-1.

    Input
    ---------------------------------------------------------------------------
    q, z: NumPy arrays, required arguments. The discrete density pairs, a
          discrete approximation of the standard normal distribution. Output
          of the function 'sampling';
    k: int, required argument. The number of time steps. k-1 is the number of
       transition matrices generated;
    tol: float, generally in scientific notation, optional argument. Set the
         precision of the solutions to the linear programming problems.
    extra_precision: bool, optional argument. If True, set the upper bound of
                     each variable p(i,j) in the LP problems to 1. Otherwise,
                     leave it to None.

    Output
    ---------------------------------------------------------------------------
    P: NumPy array. The Markov chain, whose elements are transition matrices.
       P is 2-dim if either of the following is true: k = 2, len(t_new) = 3.
       Otherwise, P is a 3-dim array with shape (k-1, len(z), len(z));
    t_new: Numpy array. Of length k+1, if the algorithm manages to generate
           the full Markov chain (both well-defined and interpolated matrices),
           or shorter, otherwise.

    How does the algorithm work?
    ---------------------------------------------------------------------------
    Suppose you start with a sequence {z(i), q(i)}, for i = 1, ..., 14, a
    14-element partition of the standard normal CDF (the space dimension)
    generated by 'sampling.py'.

    You divide the interval [0,T] (the time dimension) into k subintervals
    which could be, for instance, thought of as 'monitoring dates' for the
    value of a risky asset, and want to generate a Markov chain, say, to
    calculate the expected value of the position today.

    'lp.py' is a robust enough algorithm to return a well-defined Markov chain
    even if, for any transition matrix, one of the following occurs:
     * the optimisation algorithm is unable to find a feasible starting point
       (exit: 2);
     * the optimisation is successful (exit: 0) but the value of the function
       is wrong, either negative or greater than zero;
     * the iteration limit is reached (exit: 1);

    In such circumstances, the function automatically:
     - decreases tolerance level, e.g. from 1e-9 to 1e-8, and starts from
       scratch until a feasible solution is found;
     - only stops whenever tolerance is a number bigger than 1e-2, in which
       case the solution would be highly imprecise.

    If, despite the procedure above, still no solution is found, the algorithm
    automatically tries to replace the badly specified transition matrix with
    one obtained by interpolating the two nearest well-defined matrices.

    Two cases are possible:
     * the bad matrix occurs at the end of the Markov chain: in this case, the
       matrix is automatically scrapped, because no matrix on the right can be
       used for interpolation;
     * the bad matrix is an intermediate one: in this case, it is successfully
       interpolated.

    If necessary, the length of t is automatically adjusted as a consequence
    of the shortened Markov chain, an a new vector t_new returned.

    Example
    ---------------------------------------------------------------------------
    P, t = lp(z, q, k=5, tol=1e-12, extra_precision=True)

    Generate a Markov chain of length k-1 = 4, if possible, otherwise shorter.
    Use stricter tolerance for the solutions and impose upper bound 1.
    With len(z) = len(q) = 14, matrices P[0], P[1], and P[2] are well-defined
    but P[3] is not. P[3] occurs at the end of the chain, hence it cannot be
    interpolated. With P[3] scrapped, the returned Markov chain has length k-2,
    while the new vector t = [0, ..., 0.8] has length k-1.

    Resources
    ---------------------------------------------------------------------------
    [1] Curran, M. (2001). Willow Power: Optimizing Derivative Pricing Trees,
        ALGO Research Quarterly, Vol. 4, No. 4, p. 15, December 2001.
    [2] Ho, A.C.T. (2000). Willow Tree. MSc Thesis in Mathematics, University
        of British Columbia.
    '''

    # Import required libraries
    import time
    import numpy as np
    from scipy import optimize

    def objective(z, a, beta, normalize):
        '''
        Generate objective function c in equation (1) of the LP problem.
        Normalise c if array q was obtained with gamma != 0.
        '''
        F = (np.abs(a-beta*a.transpose()) ** 3).transpose()\
            .reshape(len(z)**2)
        c = F * normalize
        return c

    def beq(q, u, z, beta, Aeq):
        '''
        Generate b_eq, the vector of linear equality constraints in equation
        (2) of the LP problem.
        '''
        beq = np.array([u, beta*z, (beta**2)*r + (1-beta**2)*u,
                        q]).reshape(len(Aeq))
        return beq

    def transition_matrix(z, c, Aeq, beq, tol, extra_precision):
        '''
        Compute transition matrix P, the solution to the LP problem--x, in
        equation (1).
        '''
        # Place upper bound on each probability if extra_precision=True
        if extra_precision:
            bounds = (0, 1)
        else:
            bounds = (0, None)

        # Account for a different tolerance level, if specified
        options = {'maxiter': 1e4, 'tol': tol, 'disp': False}

        # Linear programming problem
        P = optimize.linprog(c, A_eq = Aeq, b_eq = beq,
                             bounds = bounds, method = 'simplex',
                             options = options)
        return P

    def test(n, P):
        '''
        Test whether the transition matrix generated by the LP algorithm
        satisfies the sum(p(i,:)) = 1, for all rows i. Return False otherwise.
        '''
        try:
            # Reshape P and perform test on each row; sum all columns (axis=1)
            P = P.reshape(n,n)
            return np.isclose(P.sum(axis=1), np.ones(n), 1e-6).all() == True
        except:
            return False

    def interpolate(P_min, P_max, alpha_min, alpha_max, alpha_interp):
        '''
        Interpolate a bad transition matrix using Curran's method [1].
        Return interpolated matrix.
        '''
        x1 = 1 / np.sqrt(1+alpha_min)
        x2 = 1 / np.sqrt(1+alpha_max)
        x3 = 1 / np.sqrt(1+alpha_interp)

        coeff_min = (x3-x2) / (x1-x2)
        coeff_max = (x1-x3) / (x1-x2)

        return coeff_min*P_min + coeff_max*P_max

    '''
    Store the user defined tolerance level in variable 'initial_tol'. This is
    the starting tolerance level for the solution to the LP problems.
    The variable does not change, and it is the starting point for each set of
    LP problems solved to determine a particular transition matrix. What varies
    is a new variable 'tol', which originally takes on the value 'initial_tol'
    but is then reduced by one degree of magnitude (e.g. from 1e-9 to 1e-8),
    up to 1e-2, until a solution is found. If 'tol' reaches 1e-2 and still no
    satisfactory solution is found, the transition matrix is labelled as badly
    defined, 'tol' is again set to 'initial_tol', and a new set of LP problems
    is run to determine the next transition matrix.
    '''
    initial_tol = tol

    # Set n as the number of space nodes
    n = len(z)

    # Generate the array of time nodes from k, the desired no. of time steps
    t = np.linspace(0, 1, k + 1)

    # Define auxiliary variables for c, Aeq, beq [2]
    u = np.ones(n, dtype = np.int)
    r = z ** 2
    h = t[2:] - t[1:-1]
    alpha = h / t[1:-1]
    beta = 1 / np.sqrt(1+alpha)

    '''
    Define auxiliary variables for c, the objective function. Normalise the
    objective, if necessary (if q was determined using gamma != 0).
    '''
    a = z[:, np.newaxis] @ np.ones(n)[np.newaxis]
    normalize = np.kron(q, np.ones(n))

    # Determine c, the objective function for each LP problem
    c = np.array([objective(z, a, beta[i], normalize) \
                  for i in range(len(h))])

    # Determine Aeq, the matrix of linear equality constraints [2]
    Aeq = np.vstack([np.kron(np.eye(n), u),
                     np.kron(np.eye(n), z),
                     np.kron(np.eye(n), r),
                     np.kron(q, np.eye(n))])

    # Determine beq, the array of linear equality constraints [2]
    beq = np.array([beq(q, u, z, beta[i], Aeq) \
                    for i in range(len(h))])

    # Preallocate memory for the 3-dim (or 2-dim) Markov chain
    Px = np.array([np.zeros([n, n]) \
         for i in range(len(h))])

    '''
    Initialise 1-dim array 'flag' of length h, the one assumed for the full
    Markov chain. By construction, 'flag' has null components, which are
    either left unmodified if the procedure to find a transition matrix is
    successful, or set to -1 otherwise.
    '''
    flag = np.zeros(len(h), dtype = np.int)

    '''
    Begin procedure to find transition matrix, initially shaped as a 1-dim
    array to speed computation.
    '''
    for i in range(len(h)):
        # Run one initial LP problem
        P = transition_matrix(z, c[i], Aeq, beq[i], tol,
                              extra_precision)

        # If the returned matrix != np.nan (exit != 2, see above), continue
        if type(P.x) != np.float:

            # Set timer. This will prevent the LP from being too time consuming
            start = time.time()

            '''
            Continue looking for a feasible solution unless one of the
            following occurs:
             * exit == 0 (satisfactory solution found);
             * objective function in [0;1] (well-behaved matrix);
             * all p(k; i,j) probabilities in [0;1];
             * the tests for mean, variance, and kurtosis (if applicable) are
               all passed;
            '''
            while (P.status != 0) | (P.fun < 0) | (P.fun > 1) \
                | ((P.x[P.x < 0]).any()) | ((P.x[P.x > 1]).any()) \
                | (test(n, P.x) != True):

                '''
                If no satisfactory solution is found, and if both of the
                following apply:
                 * tolerance level still smaller than 1e-3; and
                 * the elapsed time is less than one minute.
                Increase tolerance by one order of magnitude and proceed with
                a new LP problem.
                '''
                if (tol < 1e-3) & (time.time() - start < 60):
                    tol *= 10
                    P = transition_matrix(z, c[i], Aeq, beq[i], tol,
                                          extra_precision)
                else:
                    # Break process and set flag to -1 (bad matrix) otherwise
                    flag[i] = -1
                    break

            # Reshape array solution to 2-dim transition matrix
            Px[i] = P.x.reshape(n, n)

        else:
            '''
            If the returned matrix is np.nan (exit == 2), set flag to -1
            (badly defined) and pass to following matrix in the chain.
            '''
            flag[i] = -1

        # Inform user of the quality of the solution
        if flag[i] == -1:
            print('Warning: P[{}] wrongly specified.'.format(i))
            print('Replacing with interpolated matrix if possible.')
        else:
            print('P[{}] successfully generated.'.format(i))

        '''
        Set tolerance back to initial level for each new transition matrix to
        determine.
        '''
        tol = initial_tol

        '''
        Store the positions of all -1 flags in a new array 'failure' and those
        of all 0 flags in a new array 'success'.
        '''
        failure = np.nonzero(flag)[0]
        success = np.nonzero(flag + 1)[0]

    try:
        '''
        Initialise empty arrays 'minvec' and 'maxvec'. These arrays will be
        useful to determine which matrices to use in order to interpolate the
        badly defined transition matrices. Each component of 'minvec' and
        'maxvec' is, respectively, a lower and an upper bound for a bad matrix.
        For example, suppose the Markov chain is made of four matrices (k = 5)
        and the flag vector is as such:

        flag = np.array([0, -1, 0, -1])

        This means that the first and third matrices are well-defined, whereas
        the second and last ones are not. Arrays 'failure' and 'success' will
        thus be:

        failure = np.array([1, 3])
        success = np.array([0, 2])

        That is, well-defined matrices occur at position 0 and 2; bad ones at
        positions 1 and 3.

        'minvec' and 'maxvec' will then be:

        minvec = np.array([0, 2])
        maxvec = np.array([2])

        So, the first bad matrix (position 1) has two well-defined adjacent
        matrices: one in 0 (minvec element 0), the other in 2 (maxvec element
        2). The second one (position 3) has only one well-defined adjacent
        matrix, at position 2 (minvec element 2).

        As a consequence, it is possible to interpolate the first matrix using
        the adjacent arrays, but the second one needs to be scrapped.
        '''
        minvec = np.array([], dtype = np.int)
        maxvec = minvec

        '''
        To retrieve 'minvec', start from the end of the chain and proceed
        backwards, to avoid errors due to bad matrices at the beginning of
        the chain, if any.
        '''
        for i in reversed(range(len(failure))):
            minvec = np.append(minvec, [max(x for x in success \
                                            if x < failure[i])])

            # Sort ascending the resulting vector, which was computed backwards
            minvec.sort()
    except ValueError:
        pass

    '''
    Try separately for 'minvec' and 'maxvec', to prevent errors in one which
    would not occur also in the other.
    '''
    try:
        '''
        To retrieve 'maxvec', start from the beginning of the chain to avoid
        errors due to bad matrices at the end of the chain, if any.
        '''
        for i in range(len(failure)):
            maxvec = np.append(maxvec, [min(x for x in success \
                                            if x > failure[i])])
    except ValueError:
        pass

    '''
    The following lines of code align the length of 'minvec' and 'maxvec' to
    that of 'flag'. The purpose is to univocally assign unique minimum and
    maximum values to each bad transition matrix, to identify the indices of
    the adjacent matrices to be used in the interpolation step. An example
    should clarify. Consider the following 'flag' vector:

    flag = np.array([-1, 0, 0, -1, -1, 0, -1, 0])

    The vector signals that there are bad transition matrices at positions 0,
    3-4, and 6. Before aligning size, 'minvec' and 'maxvec' are:

    minvec = np.array([2, 2, 5])
    maxvec = np.array([5, 5, 7])

    After aligning size, 'minvec' and 'maxvec' (now 'repl_min' and 'repl_max')
    become:

    repl_min = np.array([-1, -1, -1,  2,  2, -1,  5, -1])
    repl_max = np.array([-1, -1, -1,  5,  5, -1,  7, -1])

    This way, if possible, each bad matrix is univocally assigned two indices,
    a minimum and a maximum, corresponding to the positions of the matrices to
    use in the interpolation step. However, only three out of four bad matrices
    have indices assigned (the beginning one has no minimum, therefore it will
    be automatically scrapped).
    '''
    repl_min = np.full(len(flag), -1, dtype=np.int)
    repl_max = np.full(len(flag), -1, dtype=np.int)

    '''
    Replace -1 components in 'repl_min', 'repl_max', at positions corresponding
    to the values in 'minvec', 'maxvec', with positive numbers 1, then to be
    replaced by the actual components of 'minvec', 'maxvec' using masking.
    '''
    for i in failure:
        repl_min[i] = 1
        repl_max[i] = 1

    '''
    Uniform 'minvec' length to that of 'repl_min'. Only pad array with -1 on
    the left. Replace 'repl_min' components 1 with actual 'minvec' values.
    '''
    minvec = np.pad(minvec, ((len(failure)-len(minvec)),0),
                    mode='constant', constant_values=-1)
    repl_min[repl_min>0] = minvec

    '''
    Uniform 'maxvec' length to that of 'repl_max'. Only pad array with -1 on
    the right. Replace 'repl_max' components 1 with actual 'maxvec' values.
    '''
    maxvec = np.pad(maxvec, (0,len(failure) - len(maxvec)),
                    mode='constant', constant_values=-1)
    repl_max[repl_max>0] = maxvec

    succ_vec = (repl_min > -1) & (repl_min < repl_max)
    succ_vec = np.array([1 if succ_vec[i] == True else 0 for i \
                         in range(len(succ_vec))])

    try:
        threshold_low = np.argwhere(succ_vec)[0,0]
        threshold_high = np.argwhere(succ_vec)[-1,0]
    except:
        threshold_low, threshold_high = -1, -1

    failure = failure[(failure >= threshold_low) \
                    & (failure <= threshold_high)]

    minvec = repl_min * succ_vec
    maxvec = repl_max * succ_vec

    minvec = minvec[minvec > -1]
    maxvec = maxvec[maxvec > 0]

    '''
    Interpolate bad matrices according to Curran's [1] methodology. If the
    interpolation is successful, replace negative flags with 0 (success), then
    substitute the matrices in the Markov chain.
    '''
    if (flag == -1).any():
        try:
            Px[failure] = [interpolate(Px[minvec[i]], Px[maxvec[i]],
                           alpha[minvec[i]], alpha[maxvec[i]],
                           alpha[failure[i]]) for i \
                           in range(len(failure))]
        except ValueError:
            pass

        for i in failure:
            print('Interpolation of P[{}] successful.'.format(i))
        flag[failure] = 0
    else:
        pass

    success = np.nonzero(flag + 1)[0]
    Px = Px[success]

    '''
    Resize array t in case the generated Markov chain is shorter, either at
    the beginning or at the end.
    '''
    try:
        if success[0] == 0:
            t_new = t[range(len(success)+2)]
        else:
            t_new = np.append(0,t[(t >= t[success[0]+1]) \
                                & (t <= t[success[-1]+2])])

        if t_new[1] != t[1]:
            print('Warning: t has been increased. t[1] = {:.2f}'\
                  .format(t_new[1]))
        if t_new[-1] != t[-1]:
            print('Warning: t has been shortened. T = {:.2f}'\
                  .format(t_new[-1]))
    except:
        t_new = t[:2]
        print('Warning: t has been shortened. T = {:.2f}'.format(t_new[-1]))

    return Px, t_new
