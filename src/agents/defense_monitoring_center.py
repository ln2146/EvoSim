"""
EvoCorps Active Defense System - Monitoring Center
Real-time metrics dashboard for defense system performance
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
import json


@dataclass
class TopicData:
    """Data structure for a single topic"""
    topic_id: str
    topic_name: str
    engagement_count: int = 0
    malicious_posts: int = 0
    defense_posts: int = 0
    neutral_posts: int = 0
    total_likes: int = 0
    total_comments: int = 0
    top_contributors: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AccountMetrics:
    """Metrics for a single account"""
    account_id: str
    account_type: str  # "malicious", "defense", "neutral"
    followers: int = 0
    total_likes: int = 0
    total_comments: int = 0
    total_posts: int = 0
    engagement_rate: float = 0.0
    extreme_score: float = 0.0  # 0-1, higher = more extreme


class NicheOccupancyTracker:
    """
    Tracks niche occupancy - which topics are dominated by malicious bots vs EvoCorps
    """
    
    def __init__(self, top_n_topics: int = 10):
        self.top_n_topics = top_n_topics
        self.topics: Dict[str, TopicData] = {}
        self.topic_rankings: List[str] = []  # Sorted by engagement
        self.history: List[Dict[str, Any]] = []
    
    def update_topic(self, topic_data: TopicData):
        """Update or add a topic"""
        self.topics[topic_data.topic_id] = topic_data
        self._recalculate_rankings()
    
    def _recalculate_rankings(self):
        """Recalculate topic rankings by engagement"""
        sorted_topics = sorted(
            self.topics.values(),
            key=lambda t: t.engagement_count,
            reverse=True
        )
        self.topic_rankings = [t.topic_id for t in sorted_topics[:self.top_n_topics]]
    
    def get_dominance_for_topic(self, topic_id: str) -> Dict[str, float]:
        """Calculate dominance percentages for a topic"""
        topic = self.topics.get(topic_id)
        if not topic:
            return {"malicious": 0.0, "defense": 0.0, "neutral": 0.0}
        
        total = topic.malicious_posts + topic.defense_posts + topic.neutral_posts
        if total == 0:
            return {"malicious": 0.0, "defense": 0.0, "neutral": 0.0}
        
        return {
            "malicious": topic.malicious_posts / total,
            "defense": topic.defense_posts / total,
            "neutral": topic.neutral_posts / total
        }
    
    def get_topic_controller(self, topic_id: str) -> str:
        """Determine which faction controls a topic"""
        dominance = self.get_dominance_for_topic(topic_id)
        
        if dominance["malicious"] > 0.5:
            return "malicious"
        elif dominance["defense"] > 0.5:
            return "defense"
        elif dominance["malicious"] > dominance["defense"]:
            return "malicious_leaning"
        elif dominance["defense"] > dominance["malicious"]:
            return "defense_leaning"
        else:
            return "contested"
    
    def calculate_niche_occupancy(self) -> Dict[str, Any]:
        """
        Calculate niche occupancy metrics for top N topics
        
        Returns:
            Dictionary with occupancy statistics
        """
        if not self.topic_rankings:
            return {
                "total_topics": 0,
                "malicious_dominant": 0,
                "defense_dominant": 0,
                "contested": 0,
                "malicious_percentage": 0.0,
                "defense_percentage": 0.0,
                "topics_detail": []
            }
        
        malicious_dominant = 0
        defense_dominant = 0
        contested = 0
        topics_detail = []
        
        for topic_id in self.topic_rankings:
            controller = self.get_topic_controller(topic_id)
            topic = self.topics.get(topic_id)
            dominance = self.get_dominance_for_topic(topic_id)
            
            if controller == "malicious":
                malicious_dominant += 1
            elif controller == "defense":
                defense_dominant += 1
            else:
                contested += 1
            
            topics_detail.append({
                "topic_id": topic_id,
                "topic_name": topic.topic_name if topic else "Unknown",
                "controller": controller,
                "malicious_ratio": dominance["malicious"],
                "defense_ratio": dominance["defense"],
                "engagement_count": topic.engagement_count if topic else 0
            })
        
        total = len(self.topic_rankings)
        return {
            "total_topics": total,
            "malicious_dominant": malicious_dominant,
            "defense_dominant": defense_dominant,
            "contested": contested,
            "malicious_percentage": malicious_dominant / total * 100 if total > 0 else 0,
            "defense_percentage": defense_dominant / total * 100 if total > 0 else 0,
            "topics_detail": topics_detail,
            "timestamp": datetime.now().isoformat()
        }
    
    def record_snapshot(self):
        """Record current state to history"""
        snapshot = self.calculate_niche_occupancy()
        self.history.append(snapshot)
        return snapshot


class AlgorithmicBiasCalculator:
    """
    Calculates Algorithmic Bias Gini Coefficient
    Measures if traffic is overly concentrated on a few extreme accounts
    """
    
    def __init__(self):
        self.accounts: Dict[str, AccountMetrics] = {}
        self.history: List[Dict[str, Any]] = []
    
    def update_account(self, account_metrics: AccountMetrics):
        """Update or add an account"""
        self.accounts[account_metrics.account_id] = account_metrics
    
    def calculate_gini_coefficient(self, values: List[float]) -> float:
        """
        Calculate Gini coefficient for a list of values
        
        Args:
            values: List of non-negative values
        
        Returns:
            Gini coefficient (0 = perfect equality, 1 = perfect inequality)
        """
        if not values or all(v == 0 for v in values):
            return 0.0
        
        # Sort values
        sorted_values = sorted(values)
        n = len(sorted_values)
        
        # Calculate Gini coefficient
        cumsum = 0.0
        for i, v in enumerate(sorted_values):
            cumsum += (2 * (i + 1) - n - 1) * v
        
        total = sum(sorted_values)
        if total == 0:
            return 0.0
        
        gini = cumsum / (n * total)
        return max(0.0, min(1.0, gini))
    
    def calculate_traffic_concentration(self) -> Dict[str, Any]:
        """
        Calculate traffic concentration metrics
        
        Returns:
            Dictionary with concentration statistics
        """
        if not self.accounts:
            return {
                "gini_coefficient": 0.0,
                "top_10_percent_share": 0.0,
                "top_1_percent_share": 0.0,
                "extreme_account_share": 0.0,
                "total_accounts": 0,
                "total_engagement": 0
            }
        
        # Get engagement values
        engagements = [acc.total_likes + acc.total_comments for acc in self.accounts.values()]
        total_engagement = sum(engagements)
        
        if total_engagement == 0:
            return {
                "gini_coefficient": 0.0,
                "top_10_percent_share": 0.0,
                "top_1_percent_share": 0.0,
                "extreme_account_share": 0.0,
                "total_accounts": len(self.accounts),
                "total_engagement": 0
            }
        
        # Calculate Gini coefficient
        gini = self.calculate_gini_coefficient(engagements)
        
        # Sort accounts by engagement
        sorted_accounts = sorted(
            self.accounts.values(),
            key=lambda a: a.total_likes + a.total_comments,
            reverse=True
        )
        n = len(sorted_accounts)
        
        # Top 10% share
        top_10_percent_count = max(1, int(n * 0.1))
        top_10_engagement = sum(
            acc.total_likes + acc.total_comments 
            for acc in sorted_accounts[:top_10_percent_count]
        )
        top_10_share = top_10_engagement / total_engagement * 100
        
        # Top 1% share
        top_1_percent_count = max(1, int(n * 0.01))
        top_1_engagement = sum(
            acc.total_likes + acc.total_comments 
            for acc in sorted_accounts[:top_1_percent_count]
        )
        top_1_share = top_1_engagement / total_engagement * 100
        
        # Extreme account share (accounts with extreme_score > 0.7)
        extreme_accounts = [acc for acc in self.accounts.values() if acc.extreme_score > 0.7]
        extreme_engagement = sum(
            acc.total_likes + acc.total_comments 
            for acc in extreme_accounts
        )
        extreme_share = extreme_engagement / total_engagement * 100
        
        return {
            "gini_coefficient": round(gini, 4),
            "top_10_percent_share": round(top_10_share, 2),
            "top_1_percent_share": round(top_1_share, 2),
            "extreme_account_share": round(extreme_share, 2),
            "extreme_account_count": len(extreme_accounts),
            "total_accounts": n,
            "total_engagement": total_engagement,
            "timestamp": datetime.now().isoformat()
        }
    
    def calculate_algorithmic_bias_gini(self) -> Dict[str, Any]:
        """
        Calculate algorithmic bias specifically for extreme vs moderate content
        
        Returns:
            Dictionary with bias metrics
        """
        if not self.accounts:
            return {
                "overall_gini": 0.0,
                "malicious_gini": 0.0,
                "defense_gini": 0.0,
                "neutral_gini": 0.0,
                "bias_assessment": "unknown"
            }
        
        # Separate by account type
        malicious_engagements = [
            acc.total_likes + acc.total_comments 
            for acc in self.accounts.values() 
            if acc.account_type == "malicious"
        ]
        defense_engagements = [
            acc.total_likes + acc.total_comments 
            for acc in self.accounts.values() 
            if acc.account_type == "defense"
        ]
        neutral_engagements = [
            acc.total_likes + acc.total_comments 
            for acc in self.accounts.values() 
            if acc.account_type == "neutral"
        ]
        
        all_engagements = [
            acc.total_likes + acc.total_comments 
            for acc in self.accounts.values()
        ]
        
        overall_gini = self.calculate_gini_coefficient(all_engagements)
        malicious_gini = self.calculate_gini_coefficient(malicious_engagements)
        defense_gini = self.calculate_gini_coefficient(defense_engagements)
        neutral_gini = self.calculate_gini_coefficient(neutral_engagements)
        
        # Assess bias level
        if overall_gini > 0.7:
            bias_assessment = "severe_concentration"
        elif overall_gini > 0.5:
            bias_assessment = "high_concentration"
        elif overall_gini > 0.3:
            bias_assessment = "moderate_concentration"
        else:
            bias_assessment = "healthy_distribution"
        
        return {
            "overall_gini": round(overall_gini, 4),
            "malicious_gini": round(malicious_gini, 4),
            "defense_gini": round(defense_gini, 4),
            "neutral_gini": round(neutral_gini, 4),
            "bias_assessment": bias_assessment,
            "timestamp": datetime.now().isoformat()
        }
    
    def record_snapshot(self) -> Dict[str, Any]:
        """Record current state to history"""
        concentration = self.calculate_traffic_concentration()
        bias = self.calculate_algorithmic_bias_gini()
        
        snapshot = {
            **concentration,
            **bias
        }
        self.history.append(snapshot)
        return snapshot


class DefenseMonitoringCenter:
    """
    Central monitoring hub for EvoCorps defense system
    Aggregates all metrics and provides real-time dashboard
    """
    
    def __init__(self, top_n_topics: int = 10):
        self.niche_tracker = NicheOccupancyTracker(top_n_topics)
        self.bias_calculator = AlgorithmicBiasCalculator()
        self.dashboard_history: List[Dict[str, Any]] = []
        self.alerts: List[Dict[str, Any]] = []
    
    def update_topic_data(self, topic_data: TopicData):
        """Update topic data"""
        self.niche_tracker.update_topic(topic_data)
    
    def update_account_data(self, account_metrics: AccountMetrics):
        """Update account data"""
        self.bias_calculator.update_account(account_metrics)
    
    def generate_dashboard(self) -> Dict[str, Any]:
        """
        Generate comprehensive dashboard with all metrics
        
        Returns:
            Complete dashboard data
        """
        niche_occupancy = self.niche_tracker.calculate_niche_occupancy()
        traffic_concentration = self.bias_calculator.calculate_traffic_concentration()
        algorithmic_bias = self.bias_calculator.calculate_algorithmic_bias_gini()
        
        # Generate alerts if needed
        self._check_alerts(niche_occupancy, traffic_concentration, algorithmic_bias)
        
        dashboard = {
            "timestamp": datetime.now().isoformat(),
            "niche_occupancy": niche_occupancy,
            "traffic_concentration": traffic_concentration,
            "algorithmic_bias": algorithmic_bias,
            "alerts": self.alerts[-5:] if self.alerts else [],  # Last 5 alerts
            "summary": {
                "defense_health": self._calculate_defense_health(
                    niche_occupancy, algorithmic_bias
                ),
                "recommendations": self._generate_recommendations(
                    niche_occupancy, algorithmic_bias
                )
            }
        }
        
        self.dashboard_history.append(dashboard)
        return dashboard
    
    def _check_alerts(
        self, 
        niche_occupancy: Dict[str, Any],
        traffic_concentration: Dict[str, Any],
        algorithmic_bias: Dict[str, Any]
    ):
        """Check for alert conditions"""
        # Alert: Malicious dominance in too many topics
        if niche_occupancy["malicious_percentage"] > 60:
            self.alerts.append({
                "level": "warning",
                "type": "malicious_dominance",
                "message": f"Malicious actors dominate {niche_occupancy['malicious_percentage']:.1f}% of top topics",
                "timestamp": datetime.now().isoformat()
            })
        
        # Alert: High traffic concentration
        if traffic_concentration["gini_coefficient"] > 0.7:
            self.alerts.append({
                "level": "warning",
                "type": "high_concentration",
                "message": f"Traffic highly concentrated (Gini: {traffic_concentration['gini_coefficient']:.2f})",
                "timestamp": datetime.now().isoformat()
            })
        
        # Alert: Extreme accounts getting too much engagement
        if traffic_concentration["extreme_account_share"] > 30:
            self.alerts.append({
                "level": "critical",
                "type": "extreme_amplification",
                "message": f"Extreme accounts receiving {traffic_concentration['extreme_account_share']:.1f}% of engagement",
                "timestamp": datetime.now().isoformat()
            })
    
    def _calculate_defense_health(
        self,
        niche_occupancy: Dict[str, Any],
        algorithmic_bias: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate overall defense system health score"""
        
        # Niche occupancy score (0-100)
        # Higher is better (more defense dominance)
        niche_score = niche_occupancy["defense_percentage"]
        
        # Bias health score (0-100)
        # Lower Gini is better
        bias_score = max(0, 100 - algorithmic_bias["overall_gini"] * 100)
        
        # Combined health score
        health_score = (niche_score * 0.5 + bias_score * 0.5)
        
        if health_score >= 70:
            status = "healthy"
        elif health_score >= 50:
            status = "moderate"
        elif health_score >= 30:
            status = "concerning"
        else:
            status = "critical"
        
        return {
            "score": round(health_score, 1),
            "status": status,
            "niche_score": round(niche_score, 1),
            "bias_score": round(bias_score, 1)
        }
    
    def _generate_recommendations(
        self,
        niche_occupancy: Dict[str, Any],
        algorithmic_bias: Dict[str, Any]
    ) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        # Topic-based recommendations
        if niche_occupancy["malicious_percentage"] > 50:
            recommendations.append(
                "Deploy more Amplifier agents to contested topics"
            )
        
        if niche_occupancy["contested"] > niche_occupancy["defense_dominant"]:
            recommendations.append(
                "Increase Fact Checker presence in contested discussions"
            )
        
        # Bias-based recommendations
        if algorithmic_bias["overall_gini"] > 0.6:
            recommendations.append(
                "Niche Fillers should introduce alternative topics to diversify engagement"
            )
        
        if algorithmic_bias.get("extreme_account_share", 0) > 25:
            recommendations.append(
                "Empaths should engage with extreme content audiences to reduce polarization"
            )
        
        if not recommendations:
            recommendations.append("Defense system operating within normal parameters")
        
        return recommendations
    
    def get_historical_trend(self, metric: str = "all", limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get historical trend data
        
        Args:
            metric: "niche_occupancy", "algorithmic_bias", or "all"
            limit: Number of historical entries to return
        
        Returns:
            List of historical data points
        """
        history = self.dashboard_history[-limit:]
        
        if metric == "niche_occupancy":
            return [{
                "timestamp": h["timestamp"],
                "niche_occupancy": h["niche_occupancy"]
            } for h in history]
        elif metric == "algorithmic_bias":
            return [{
                "timestamp": h["timestamp"],
                "algorithmic_bias": h["algorithmic_bias"]
            } for h in history]
        else:
            return history
    
    def export_dashboard(self, format: str = "json") -> str:
        """Export dashboard data"""
        dashboard = self.generate_dashboard()
        
        if format == "json":
            return json.dumps(dashboard, indent=2, ensure_ascii=False)
        else:
            return str(dashboard)
    
    def print_dashboard_summary(self):
        """Print a formatted summary of the dashboard"""
        dashboard = self.generate_dashboard()
        
        print("\n" + "="*60)
        print("       EvoCorps Defense System Dashboard")
        print("="*60)
        print(f"\nTimestamp: {dashboard['timestamp']}")
        
        # Niche Occupancy
        no = dashboard["niche_occupancy"]
        print("\n--- Niche Occupancy (Top Topics) ---")
        print(f"  Total Topics Monitored: {no['total_topics']}")
        print(f"  Defense Dominant: {no['defense_dominant']} ({no['defense_percentage']:.1f}%)")
        print(f"  Malicious Dominant: {no['malicious_dominant']} ({no['malicious_percentage']:.1f}%)")
        print(f"  Contested: {no['contested']}")
        
        # Traffic Concentration
        tc = dashboard["traffic_concentration"]
        print("\n--- Traffic Concentration ---")
        print(f"  Gini Coefficient: {tc['gini_coefficient']:.4f}")
        print(f"  Top 10% Share: {tc['top_10_percent_share']:.1f}%")
        print(f"  Top 1% Share: {tc['top_1_percent_share']:.1f}%")
        print(f"  Extreme Account Share: {tc['extreme_account_share']:.1f}%")
        
        # Algorithmic Bias
        ab = dashboard["algorithmic_bias"]
        print("\n--- Algorithmic Bias Assessment ---")
        print(f"  Overall Gini: {ab['overall_gini']:.4f}")
        print(f"  Assessment: {ab['bias_assessment']}")
        
        # Health Summary
        health = dashboard["summary"]["defense_health"]
        print("\n--- Defense Health ---")
        print(f"  Overall Score: {health['score']}/100")
        print(f"  Status: {health['status'].upper()}")
        
        # Alerts
        if dashboard["alerts"]:
            print("\n--- Recent Alerts ---")
            for alert in dashboard["alerts"][-3:]:
                print(f"  [{alert['level'].upper()}] {alert['message']}")
        
        # Recommendations
        print("\n--- Recommendations ---")
        for rec in dashboard["summary"]["recommendations"]:
            print(f"  • {rec}")
        
        print("\n" + "="*60)


# Convenience function for quick dashboard creation
def create_monitoring_center(top_n_topics: int = 10) -> DefenseMonitoringCenter:
    """Create and return a new monitoring center instance"""
    return DefenseMonitoringCenter(top_n_topics=top_n_topics)