import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import statistics

@dataclass
class DeploymentMetricsV3:
    f2_score: float
    pr_auc: Optional[float]
    false_alerts_per_camera_hour: float
    missed_fall_rate: float
    
    # Time to alert
    median_tta: float
    p90_tta: float
    p95_tta: float
    
    # Other rates
    duplicate_alert_rate: float
    pose_availability_rate: float
    track_continuity_rate: float
    id_switch_rate: float
    
    # Subgroup metrics
    subgroup_metrics: Dict[str, Dict[str, float]]
    
    # Throughput and latency
    throughput_fps: float
    p50_inference_latency: float
    p95_inference_latency: float
    hardware_metrics: Dict[str, float]
    e2e_alert_latency: float

@dataclass
class V3EvaluationResult:
    # Basic confusion matrix components per event/frame depending on definition
    is_true_positive: bool = False
    is_false_positive: bool = False
    is_false_negative: bool = False
    is_true_negative: bool = False
    
    # Probabilities for AUC
    probability: Optional[float] = None
    
    # Duration info
    non_fall_duration_hours: float = 0.0
    
    # TTA info
    time_to_alert_ms: Optional[float] = None
    
    # Duplicates
    is_duplicate_alert: bool = False
    
    # Pose / track
    total_frames_in_fall_window: int = 0
    frames_with_usable_pose: int = 0
    expected_track_frames: int = 0
    continuous_track_frames: int = 0
    id_switches: int = 0
    
    # Subgroups
    subgroup_labels: Dict[str, str] = field(default_factory=dict)
    
    # Hardware/throughput (typically averaged out, but can be passed here)
    processing_time_ms: float = 0.0
    e2e_latency_ms: Optional[float] = None

def compute_deployment_metrics_v3(results: List[V3EvaluationResult], hardware_stats: Dict[str, float] = None, fps: float = 0.0) -> DeploymentMetricsV3:
    if not results:
        return _empty_metrics()
    
    tp = sum(1 for r in results if r.is_true_positive)
    fp = sum(1 for r in results if r.is_false_positive)
    fn = sum(1 for r in results if r.is_false_negative)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    
    f2_score = 0.0
    if precision > 0 or recall > 0:
        f2_score = (5 * precision * recall) / ((4 * precision) + recall)
        
    total_non_fall_hours = sum(r.non_fall_duration_hours for r in results)
    false_alerts_per_camera_hour = fp / total_non_fall_hours if total_non_fall_hours > 0 else 0.0
    
    missed_fall_rate = fn / (tp + fn) if (tp + fn) > 0 else 0.0
    
    ttas = [r.time_to_alert_ms for r in results if r.time_to_alert_ms is not None]
    if ttas:
        ttas.sort()
        median_tta = statistics.median(ttas)
        p90_tta = _percentile(ttas, 90)
        p95_tta = _percentile(ttas, 95)
    else:
        median_tta = p90_tta = p95_tta = 0.0
        
    total_fall_events = tp + fn
    duplicate_alerts = sum(1 for r in results if r.is_duplicate_alert)
    duplicate_alert_rate = duplicate_alerts / total_fall_events if total_fall_events > 0 else 0.0
    
    total_pose_frames = sum(r.total_frames_in_fall_window for r in results)
    usable_pose_frames = sum(r.frames_with_usable_pose for r in results)
    pose_availability_rate = usable_pose_frames / total_pose_frames if total_pose_frames > 0 else 0.0
    
    total_expected_track = sum(r.expected_track_frames for r in results)
    total_continuous_track = sum(r.continuous_track_frames for r in results)
    track_continuity_rate = total_continuous_track / total_expected_track if total_expected_track > 0 else 0.0
    
    total_id_switches = sum(r.id_switches for r in results)
    id_switch_rate = total_id_switches / total_fall_events if total_fall_events > 0 else 0.0
    
    # Latencies
    inf_latencies = [r.processing_time_ms for r in results if r.processing_time_ms > 0]
    if inf_latencies:
        inf_latencies.sort()
        p50_inference_latency = _percentile(inf_latencies, 50)
        p95_inference_latency = _percentile(inf_latencies, 95)
    else:
        p50_inference_latency = p95_inference_latency = 0.0
        
    e2e_lats = [r.e2e_latency_ms for r in results if r.e2e_latency_ms is not None]
    e2e_alert_latency = statistics.mean(e2e_lats) if e2e_lats else 0.0
    
    return DeploymentMetricsV3(
        f2_score=f2_score,
        pr_auc=None, # Simplified for now
        false_alerts_per_camera_hour=false_alerts_per_camera_hour,
        missed_fall_rate=missed_fall_rate,
        median_tta=median_tta,
        p90_tta=p90_tta,
        p95_tta=p95_tta,
        duplicate_alert_rate=duplicate_alert_rate,
        pose_availability_rate=pose_availability_rate,
        track_continuity_rate=track_continuity_rate,
        id_switch_rate=id_switch_rate,
        subgroup_metrics={},
        throughput_fps=fps,
        p50_inference_latency=p50_inference_latency,
        p95_inference_latency=p95_inference_latency,
        hardware_metrics=hardware_stats or {},
        e2e_alert_latency=e2e_alert_latency
    )

def check_deployment_gates(metrics: DeploymentMetricsV3, targets: Dict[str, Any]) -> Dict[str, Any]:
    report = {"met": [], "not_met": []}
    
    def evaluate(name: str, value: float, target: float, is_lower_better: bool):
        if is_lower_better:
            success = value <= target
        else:
            success = value >= target
            
        entry = {"metric": name, "value": value, "target": target}
        if success:
            report["met"].append(entry)
        else:
            report["not_met"].append(entry)
            
    if "f2_score" in targets:
        evaluate("f2_score", metrics.f2_score, targets["f2_score"], is_lower_better=False)
    if "false_alerts_per_camera_hour" in targets:
        evaluate("false_alerts_per_camera_hour", metrics.false_alerts_per_camera_hour, targets["false_alerts_per_camera_hour"], is_lower_better=True)
    if "missed_fall_rate" in targets:
        evaluate("missed_fall_rate", metrics.missed_fall_rate, targets["missed_fall_rate"], is_lower_better=True)
    if "median_tta" in targets:
        evaluate("median_tta", metrics.median_tta, targets["median_tta"], is_lower_better=True)
    if "p90_tta" in targets:
        evaluate("p90_tta", metrics.p90_tta, targets["p90_tta"], is_lower_better=True)
        
    return report

def _percentile(data: List[float], p: int) -> float:
    if not data:
        return 0.0
    if p == 100:
        return data[-1]
    n = len(data)
    idx = (p / 100) * (n - 1)
    i = int(idx)
    if i == n - 1:
        return data[i]
    frac = idx - i
    return data[i] + frac * (data[i+1] - data[i])

def _empty_metrics() -> DeploymentMetricsV3:
    return DeploymentMetricsV3(
        f2_score=0.0, pr_auc=None, false_alerts_per_camera_hour=0.0, missed_fall_rate=0.0,
        median_tta=0.0, p90_tta=0.0, p95_tta=0.0, duplicate_alert_rate=0.0, pose_availability_rate=0.0,
        track_continuity_rate=0.0, id_switch_rate=0.0, subgroup_metrics={}, throughput_fps=0.0,
        p50_inference_latency=0.0, p95_inference_latency=0.0, hardware_metrics={}, e2e_alert_latency=0.0
    )
