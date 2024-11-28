import itertools
from collections import Counter
from typing import List, Tuple, Union

import matplotlib.pyplot as plt
import numpy as np
import scipy.linalg as la
from matplotlib.ticker import MaxNLocator
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sympy import Monomial

from src.modules import noise_level

"""
Parts of the following class are adapted from their notebook, which can be found at the
following GitHub repository: 
https://github.com/unitaryfund/research/blob/main/lre/layerwise_richardson_extrapolation.ipynb.
"""


class ZeroNoiseExtrapolation:

    def __init__(
        self, datapoints: List[Tuple[Union[int, float], ...]], degree: int, method: str, sampling: str
    ) -> None:

        self.datapoints = datapoints
        self.degree = degree
        self.method = method
        self.sampling = sampling

        self.unknown_var = len(datapoints[0]) - 1
        self.noise_data = [tuple(point[: self.unknown_var]) for point in self.datapoints]
        self.expectation_vals = [point[-1] for point in datapoints]

    def get_noise_levels(self) -> List[Tuple[int]]:
        """
        Returns a list containing all the noise-level values (independent variable values) extracted from the given datapoints.
        """
        return self.noise_data

    def get_expec_vals(self) -> List[float]:
        """
        Returns a list containing all the expectations values (dependent variable values) extracted from the given datapoints.
        """
        return self.expectation_vals

    def get_required_points(self) -> int:
        """
        Returns the number of datapoints required in order to perform Richardson extrapolation at a given degree and independent variables.
        """
        monomials = self.get_monomials(self.unknown_var, self.degree)
        return len(monomials)

    def get_independent_var(self) -> int:
        """
        Returns the unmber of independent variables.
        """
        return self.unknown_var

    def mul_RichardsonZNE(self) -> float:

        if self.sampling.lower() == "default":
            number_of_required_points = self.get_required_points()
            richardson_datapoints = self.datapoints[:number_of_required_points]
            richardson_noise_vals = [tuple(point[: self.unknown_var]) for point in richardson_datapoints]
            richardson_expectation_vals = [point[-1] for point in richardson_datapoints]

        # Forgot what "default" samping is supposed to do.

        else:
            raise ValueError(
                "Some error occurred. I actually forgot what the default sampling was supposed to do! If you figure it out, please fix this else-block."
            )

        RichardsonZNEval = 0
        sampleMatrix = self.sample_matrix(sample_points=richardson_noise_vals, degree=self.degree)  # type: ignore
        detA = np.linalg.det(sampleMatrix)
        if abs(detA) <= 1e-9:
            raise ValueError(f"Determinant of sample matrix is/close to zero. Det: {detA}, Deg: {self.degree}")
        # elif abs(detA) >= 1e+50:
        #     raise ValueError(f"Determinant of sample matrix close to inf. Det: {detA}, Deg: {self.degree}")

        matrices = self.generate_modified_matrices(sampleMatrix)  # type: ignore

        if len(richardson_expectation_vals) != len(matrices):
            raise ValueError(f"Unmatched length.")

        for E, matrix in zip(richardson_expectation_vals, matrices):
            eta = np.linalg.det(matrix) / detA
            E = np.array(E)
            RichardsonZNEval += E * eta
            eta = 0

        return RichardsonZNEval

    def getRichardsonZNE(self) -> float:


        if self.method.lower() == "richardson-mul":
            zne_val = self.mul_RichardsonZNE()

        elif self.method.lower() == "richardson":
            zne_val = self.getRichardsonZNE2()

        elif self.method.lower() == "linear":
            zne_val = self.scikit_linear()

        elif self.method.lower() == "polynomial":
            zne_val = self.scikit_poly()
        
        else:
            raise ValueError(f"Invalid method: {self.method}. Valid methods are: richardson-m, richardson, linear, and polynomial.")

        return zne_val

    @staticmethod
    def get_monomials(n: int, d: int) -> list[str]:
        """
        Compute monomials of degree `d` in graded lexicographical order.
        """
        variables = [f"λ_{i}" for i in range(1, n + 1)]

        monomials = []
        for degree in range(d, -1, -1):
            # Generate combinations for the current degree
            combos = list(itertools.combinations_with_replacement(variables, degree))

            # Sort combinations lexicographically
            combos.sort()

            # Construct monomials from sorted combinations
            for combo in combos:
                monomial_parts = []
                counts = Counter(combo)
                # Ensure variables are processed in lexicographical order
                for var in sorted(counts.keys()):
                    count = counts[var]
                    if count > 1:
                        monomial_parts.append(f"{var}**{count}")
                    else:
                        monomial_parts.append(var)
                monomial = "*".join(monomial_parts)
                # Handle the case where degree is 0
                if not monomial:
                    monomial = "1"
                monomials.append(monomial)
        # "1" should be the first monomial. Note that order d > c > b > a means vector of monomials = [a, b, c, d].
        return monomials[::-1]

    @staticmethod
    def sample_matrix(sample_points: list[int], degree: int) -> np.ndarray:
        """Construct a matrix from monomials evaluated at sample points."""
        n = len(sample_points[0])  # type: ignore # Number of variables based on the first sample point
        monomials = ZeroNoiseExtrapolation.get_monomials(n, degree)  # type: ignore
        matrix = np.zeros((len(sample_points), len(monomials)))

        for i, point in enumerate(sample_points):
            for j, monomial in enumerate(monomials):
                var_mapping = {f"λ_{k+1}": point[k] for k in range(n)}  # type: ignore
                matrix[i, j] = eval(monomial, {}, var_mapping)
        return matrix

    @staticmethod
    def get_eta_coeffs_from_sample_matrix(mat: np.ndarray) -> list[float]:
        """Given a sample matrix compute the eta coefficients."""
        n_rows, n_cols = mat.shape
        if n_rows != n_cols:
            raise ValueError("The matrix must be square.")

        det_m = np.linalg.det(mat)
        if det_m == 0:
            raise ValueError("The matrix is singular.")

        terms = []
        for i in range(n_rows):
            new_mat = mat.copy()
            new_mat[i] = np.array([[0] * (n_cols - 1) + [1]])
            terms.append(np.linalg.det(new_mat) / det_m)

        return terms

    @staticmethod
    def get_eta_coeffs_single_variable(scale_factors: list[float]) -> list[float]:
        """Returns the array of single-variable Richardson extrapolation coefficients associated
        to the input array of scale factors."""

        # Lagrange interpolation formula.
        richardson_coeffs = []
        for l in scale_factors:
            coeff = 1.0
            for l_prime in scale_factors:
                if l_prime == l:
                    continue
                coeff *= l_prime / (l_prime - l)
            richardson_coeffs.append(coeff)

        return richardson_coeffs

    @staticmethod
    def generate_modified_matrices(matrix):
        """
        It generates the Mi(0) matreces for i = 1 to length of sample matrix.
        See this papaer for the detail mathematical formalism:
        "Quantum error mitigation by layerwise Richardson extrapolation" by Vincent Russo, Andrea Mari, https://arxiv.org/abs/2402.04000
        """
        n = len(matrix)  # Size of the square matrix
        identity_row = [1] + [0] * (n - 1)  # Row to replace with

        modified_matrices = []
        determinants = []
        for i in range(n):
            # Create a copy of the original matrix
            modified_matrix = np.copy(matrix)
            # Replace the i-th row with the identity_row
            modified_matrix[i] = identity_row
            modified_matrices.append(modified_matrix)
            # Calculate the determinant of the modified matrix
            determinant = np.linalg.det(modified_matrix)
            determinants.append(determinant)

        return modified_matrices

    # Standard single variate Richardson Extrapolation
    def getRichardsonZNE2(self):
        richardson_datapoints = self.datapoints
        # Sum the noisy gate values (multivariate noise) to get total noise (single variate noise)
        total_noise = [sum(point[:3]) for point in richardson_datapoints]
        richardson_expectation_vals = [point[-1] for point in richardson_datapoints]

        betas = []
        for k in range(len(total_noise)):
            alpha_k = total_noise[k]
            product = 1
            for i in range(len(total_noise)):
                if i != k:
                    alpha_i = total_noise[i]
                    # Check if alpha_k == alpha_i to avoid division by zero
                    if alpha_k != alpha_i:
                        product *= alpha_i / (alpha_k - alpha_i)
                    else:
                        print(
                            f"Skipping i={i}, k={k} because alpha_k == alpha_i (alpha_k={alpha_k}, alpha_i={alpha_i})"
                        )
            betas.append(product)

        zne_val = sum(betas[i] * richardson_expectation_vals[i] for i in range(len(betas)))

        return zne_val

    def scikit_linear(self) -> float:
        # Extract noise levels (nR, nT, nY) and energy values from datapoints
        noise = np.array([point[:3] for point in self.datapoints])  # Extract the noise levels
        energy = np.array([point[3] for point in self.datapoints])  # Extract the energy values

        # Create a Linear Regression model
        model = LinearRegression()

        # Train the model on the data
        model.fit(noise, energy)

        # Extrapolate the energy value for the noise level (0, 0, 0)
        extrapolated_value = model.predict([[0, 0, 0]])[0]

        # Return the predicted energy value at (0, 0, 0)
        return extrapolated_value

    def scikit_poly(self) -> float:
        # Step 1: Extract features (noise levels) and target (energy values)
        noise = np.array([point[:3] for point in self.datapoints])  # Extract the noise levels (nR, nT, nY)
        energy = np.array([point[3] for point in self.datapoints])  # Extract the energy values

        # Step 2: Create polynomial features based on the degree specified
        poly = PolynomialFeatures(degree=self.degree)
        noise_poly = poly.fit_transform(noise)  # Transform the input data into polynomial features

        # Step 3: Create and fit the linear regression model
        model = LinearRegression()
        model.fit(noise_poly, energy)  # Fit the model to the polynomial-transformed data

        # Step 4: Extrapolate the energy value for the noise level (0, 0, 0)
        # Transform (0, 0, 0) into polynomial features and predict the energy value
        zero_noise = poly.transform([[0, 0, 0]])  # Transform the (0, 0, 0) noise level into polynomial features
        extrapolated_value = model.predict(zero_noise)[0]  # Predict the energy value at (0, 0, 0)

        # Return the predicted energy value
        return extrapolated_value
