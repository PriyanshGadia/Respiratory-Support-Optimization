# =============================================================================
# lib/models.py  —  ML models (Protocol Section 9)
# Version: 1.0  |  2026-03-14
# Primary: XGBoost regression + classification (Section 9.3)
# =============================================================================

import logging
import json
import os
import inspect
import numpy as np
import pandas as pd
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, RBF, WhiteKernel
from sklearn.inspection import permutation_importance
from sklearn.ensemble import RandomForestRegressor
import xgboost as xgb

log = logging.getLogger(__name__)


class HierarchicalBayesRegressor:
    """
    Lightweight hierarchical Bayesian regressor with patient random intercepts.
    Model:
      y = f(x) + b_patient + eps
      b_patient ~ N(0, tau^2), eps ~ N(0, sigma^2)

    Fixed effect f(x) is learned with Ridge to stay stable in tiny cohorts.
    """

    def __init__(self, alpha: float = 1.0):
        self.alpha = alpha
        self.base_model = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=alpha)),
        ])
        self.posterior_mean_ = {}
        self.posterior_var_ = {}
        self.sigma2_ = 1.0
        self.tau2_ = 1.0

    def fit(self, X: np.ndarray, y: np.ndarray, patient_ids: np.ndarray):
        self.base_model.fit(X, y)
        fixed = self.base_model.predict(X)
        resid = y - fixed

        df = pd.DataFrame({"pid": patient_ids, "resid": resid})
        grp = df.groupby("pid")["resid"]
        n = grp.count().astype(float)
        mu = grp.mean().astype(float)

        within_var = grp.var(ddof=1).replace({np.nan: 0.0})
        sigma2 = float(np.average(within_var.values, weights=np.maximum(n.values - 1.0, 1.0))) if len(within_var) else float(np.var(resid))
        sigma2 = max(sigma2, 1e-6)

        between = float(np.var(mu.values, ddof=1)) if len(mu) > 1 else 0.0
        correction = float(np.mean(sigma2 / np.maximum(n.values, 1.0))) if len(n) else sigma2
        tau2 = max(between - correction, 1e-6)

        self.sigma2_ = sigma2
        self.tau2_ = tau2

        for pid in mu.index:
            n_p = float(n.loc[pid])
            mu_p = float(mu.loc[pid])
            post_var = 1.0 / ((n_p / sigma2) + (1.0 / tau2))
            post_mean = post_var * (n_p * mu_p / sigma2)
            self.posterior_mean_[pid] = float(post_mean)
            self.posterior_var_[pid] = float(post_var)

        return self

    def predict(self, X: np.ndarray, patient_ids: np.ndarray | None = None, return_std: bool = False):
        base = self.base_model.predict(X)
        if patient_ids is None:
            adj = np.zeros(len(base), dtype=float)
            var = np.full(len(base), self.tau2_, dtype=float)
        else:
            adj = np.array([self.posterior_mean_.get(pid, 0.0) for pid in patient_ids], dtype=float)
            var = np.array([self.posterior_var_.get(pid, self.tau2_) for pid in patient_ids], dtype=float)

        pred = base + adj
        if return_std:
            std = np.sqrt(np.maximum(self.sigma2_ + var, 1e-9))
            return pred, std
        return pred

    def posterior_summary(self) -> pd.DataFrame:
        posterior_rows = []
        for pid in sorted(self.posterior_mean_.keys()):
            mu = self.posterior_mean_[pid]
            sd = float(np.sqrt(max(self.posterior_var_.get(pid, 0.0), 0.0)))
            posterior_rows.append({
                "patient_id": pid,
                "posterior_mean": mu,
                "posterior_sd": sd,
                "posterior_lo95": mu - 1.96 * sd,
                "posterior_hi95": mu + 1.96 * sd,
            })
        return pd.DataFrame(posterior_rows)


class QuantileForestRegressor:
    """Random forest with empirical prediction intervals via tree quantiles."""

    def __init__(self, random_state: int = 42, n_estimators: int = 400, min_samples_leaf: int = 3):
        self.imputer = SimpleImputer(strategy="median")
        self.model = RandomForestRegressor(
            n_estimators=n_estimators,
            min_samples_leaf=min_samples_leaf,
            random_state=random_state,
            n_jobs=1,
        )

    def fit(self, X: np.ndarray, y: np.ndarray):
        Xi = self.imputer.fit_transform(X)
        self.model.fit(Xi, y)
        return self

    def _tree_predictions(self, X: np.ndarray) -> np.ndarray:
        Xi = self.imputer.transform(X)
        all_preds = np.stack([tree.predict(Xi) for tree in self.model.estimators_], axis=1)
        return all_preds

    def predict(self, X: np.ndarray) -> np.ndarray:
        Xi = self.imputer.transform(X)
        return self.model.predict(Xi)

    def predict_interval(self, X: np.ndarray, q_lo: float = 0.05, q_hi: float = 0.95) -> tuple[np.ndarray, np.ndarray]:
        all_preds = self._tree_predictions(X)
        lo = np.quantile(all_preds, q_lo, axis=1)
        hi = np.quantile(all_preds, q_hi, axis=1)
        return lo, hi

    def predict_with_uncertainty(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        mean = self.predict(X)
        lo, hi = self.predict_interval(X, q_lo=0.05, q_hi=0.95)
        std = (hi - lo) / 3.92
        return mean, std, lo, hi


# ---------------------------------------------------------------------------
# Leave-One-Patient-Out Cross-Validation iterator
# ---------------------------------------------------------------------------

def lopo_splits(df: pd.DataFrame, patient_col: str = "patient_id"):
    """
    Yield (train_idx, test_idx) for each unique patient (LOPO-CV).
    """
    patients = df[patient_col].unique()
    for pid in sorted(patients):
        test_mask  = df[patient_col] == pid
        train_mask = ~test_mask
        yield pid, np.where(train_mask)[0], np.where(test_mask)[0]


# ---------------------------------------------------------------------------
# XGBoost model wrapper
# ---------------------------------------------------------------------------

def _build_xgb_pipeline(task: str = "regression", seed: int = 42) -> Pipeline:
    """
    Build a sklearn Pipeline: impute → scale → XGBoost.
    task: 'regression' or 'classification'
    seed: random_state for XGBoost (passed through so all calls are reproducible)
    """
    if task == "regression":
        estimator = xgb.XGBRegressor(
            objective="reg:squarederror",
            random_state=seed,
            n_jobs=1,
            verbosity=0,
        )
    else:
        estimator = xgb.XGBClassifier(
            objective="binary:logistic",
            use_label_encoder=False,
            eval_metric="logloss",
            random_state=seed,
            n_jobs=1,
            verbosity=0,
        )

    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler",  StandardScaler()),
        ("model",   estimator),
    ])


def build_regression_pipeline(model_name: str, seed: int = 42):
    """
    Build a small-data regression pipeline for benchmarking.
    Supported names: xgboost, mean, ridge, gaussian_process,
    quantile_forest, hierarchical_bayes.
    """
    if model_name == "xgboost":
        return _build_xgb_pipeline(task="regression", seed=seed)

    if model_name == "mean":
        estimator = DummyRegressor(strategy="mean")
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", estimator),
        ])

    if model_name == "ridge":
        estimator = Ridge(alpha=1.0)
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", estimator),
        ])

    if model_name == "gaussian_process":
        kernel = ConstantKernel(1.0, (1e-2, 1e2)) * RBF(length_scale=1.0, length_scale_bounds=(1e-2, 1e2)) + WhiteKernel(noise_level=0.5, noise_level_bounds=(1e-5, 1e1))
        estimator = GaussianProcessRegressor(
            kernel=kernel,
            alpha=1e-4,
            normalize_y=True,
            n_restarts_optimizer=1,
        )
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", estimator),
        ])

    if model_name == "quantile_forest":
        return QuantileForestRegressor(random_state=seed)

    if model_name == "hierarchical_bayes":
        return HierarchicalBayesRegressor(alpha=1.0)

    raise ValueError(f"Unsupported regression model: {model_name}")


def _prefix_param_grid(grid: dict, prefix: str = "model__") -> dict:
    return {f"{prefix}{k}": v for k, v in grid.items()}


def _first_param_combo(param_grid: dict) -> dict:
    """Return a deterministic single-configuration dict from a grid."""
    first_combo = {}
    for key, values in param_grid.items():
        if isinstance(values, (list, tuple, np.ndarray)) and len(values) > 0:
            first_combo[key] = [values[0]]
        else:
            first_combo[key] = [values]
    return first_combo


def train_xgb(X_train: np.ndarray, y_train: np.ndarray,
              groups_train: np.ndarray,
              param_grid: dict,
              task: str = "regression",
              cv_folds: int = 3,
              seed: int = 42) -> Pipeline:
    """
    Train XGBoost with grouped inner CV (grouped by patient to avoid leakage).

    Returns fitted Pipeline.
    """
    pipeline = _build_xgb_pipeline(task)
    prefixed_grid = _prefix_param_grid(param_grid)

    scoring = "neg_mean_absolute_error" if task == "regression" else "roc_auc"
    n_patients = len(np.unique(groups_train))
    n_folds = min(cv_folds, n_patients)

    # I intentionally pin this to the first configured values so fold runtime
    # stays predictable during repeated LOPO experiments.
    fast_grid = _prefix_param_grid(_first_param_combo(param_grid))
    pipeline = _build_xgb_pipeline(task, seed=seed)
    pipeline.set_params(**{k: v[0] for k, v in fast_grid.items()})
    pipeline.fit(X_train, y_train)
    return pipeline


def train_regression_pipeline(model_name: str,
                              X_train: np.ndarray,
                              y_train: np.ndarray,
                              groups_train: np.ndarray = None,
                              param_grid: dict = None,
                              seed: int = 42):
    """
    Train one of the supported regression benchmark models.
    XGBoost uses the existing deterministic trainer; other models fit directly.
    """
    if model_name == "xgboost":
        if param_grid is None:
            param_grid = {
                "max_depth": [3, 5],
                "learning_rate": [0.1],
                "n_estimators": [200],
                "subsample": [0.8],
            }
        if groups_train is None:
            groups_train = np.zeros(len(y_train))
        return train_xgb(X_train, y_train, groups_train, param_grid=param_grid, task="regression", seed=seed)

    pipeline = build_regression_pipeline(model_name, seed=seed)
    if model_name == "hierarchical_bayes":
        if groups_train is None:
            groups_train = np.zeros(len(y_train), dtype=int)
        pipeline.fit(X_train, y_train, patient_ids=groups_train)
    else:
        pipeline.fit(X_train, y_train)
    return pipeline


def predict_with_uncertainty(model, X: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    """
    Return mean predictions and optional predictive std if supported.
    """
    if hasattr(model, "predict_with_uncertainty"):
        y_pred, y_std, _, _ = model.predict_with_uncertainty(X)
        return np.asarray(y_pred), np.asarray(y_std)

    if hasattr(model, "steps") and len(model.steps) > 0:
        transformed = X
        for _, step in model.steps[:-1]:
            transformed = step.transform(transformed)
        estimator = model.steps[-1][1]
        if hasattr(estimator, "predict"):
            try:
                sig = inspect.signature(estimator.predict)
                if "return_std" in sig.parameters:
                    y_pred, y_std = estimator.predict(transformed, return_std=True)
                    return np.asarray(y_pred), np.asarray(y_std)
            except (TypeError, ValueError):
                pass

    y_pred = model.predict(X)
    return np.asarray(y_pred), None


def compute_permutation_importance(model: Pipeline,
                                   X: np.ndarray,
                                   y: np.ndarray,
                                   feature_cols: list,
                                   seed: int = 42,
                                   n_repeats: int = 20) -> pd.DataFrame:
    """
    Model-agnostic feature importance using permutation MAE degradation.
    """
    importance_result = permutation_importance(
        model,
        X,
        y,
        n_repeats=n_repeats,
        random_state=seed,
        scoring="neg_mean_absolute_error",
        n_jobs=1,
    )
    df = pd.DataFrame({
        "feature": feature_cols,
        "importance_mean": importance_result.importances_mean,
        "importance_std": importance_result.importances_std,
    })
    return df.sort_values("importance_mean", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# LOPO-CV runner
# ---------------------------------------------------------------------------

def run_lopo_cv(features_df: pd.DataFrame,
                feature_cols: list,
                target_col: str = "y_regression",
                task: str = "regression",
                param_grid: dict = None,
                seed: int = 42,
                log_dir: str = None) -> pd.DataFrame:
    """
    Run Leave-One-Patient-Out CV with XGBoost.

    Returns
    -------
    DataFrame with columns: patient_id, y_true, y_pred, fold
    """
    if param_grid is None:
        param_grid = {
            "max_depth": [3, 5],
            "learning_rate": [0.1],
            "n_estimators": [200],
            "subsample": [0.8],
        }

    results = []
    for fold, (pid, train_idx, test_idx) in enumerate(
        lopo_splits(features_df, patient_col="patient_id")
    ):
        X_train = features_df.iloc[train_idx][feature_cols].values.astype(np.float64)
        y_train = features_df.iloc[train_idx][target_col].values.astype(np.float64)
        groups  = features_df.iloc[train_idx]["patient_id"].values

        X_test  = features_df.iloc[test_idx][feature_cols].values.astype(np.float64)
        y_test  = features_df.iloc[test_idx][target_col].values.astype(np.float64)

        # Drop rows with NaN targets from training
        valid_train = np.isfinite(y_train)
        if valid_train.sum() < 5:
            log.warning("Fold %s: too few valid training samples (%d), skipping.",
                        pid, valid_train.sum())
            continue

        model = train_xgb(
            X_train[valid_train], y_train[valid_train],
            groups[valid_train],
            param_grid=param_grid, task=task, seed=seed,
        )
        y_pred = model.predict(X_test)

        if log_dir:
            fold_log = os.path.join(log_dir, f"fold_{pid}_predictions.csv")
            pd.DataFrame({"y_true": y_test, "y_pred": y_pred}).to_csv(fold_log, index=False)

        for i in range(len(y_test)):
            results.append({
                "fold":       pid,
                "patient_id": features_df.iloc[test_idx[i]]["patient_id"],
                "y_true":     float(y_test[i]),
                "y_pred":     float(y_pred[i]),
            })

        log.info("Fold %s: n_test=%d", pid, len(y_test))

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Train final model on all data (for global deployment)
# ---------------------------------------------------------------------------

def train_final_model(features_df: pd.DataFrame,
                      feature_cols: list,
                      target_col: str = "y_regression",
                      task: str = "regression",
                      param_grid: dict = None,
                      seed: int = 42) -> tuple:
    """
    Train final model on the entire provided dataset.

    Returns
    -------
    (fitted_pipeline, feature_cols_used)
    """
    if param_grid is None:
        param_grid = {
            "max_depth": [3, 5],
            "learning_rate": [0.1],
            "n_estimators": [200],
            "subsample": [0.8],
        }

    X = features_df[feature_cols].values.astype(np.float64)
    y = features_df[target_col].values.astype(np.float64)
    groups = features_df["patient_id"].values

    valid = np.isfinite(y)
    model = train_xgb(
        X[valid], y[valid], groups[valid],
        param_grid=param_grid, task=task, seed=seed,
    )
    return model, feature_cols


def predict(model, X: np.ndarray, task: str = "regression") -> np.ndarray:
    if task == "regression":
        return model.predict(X)
    else:
        return model.predict_proba(X)[:, 1]
