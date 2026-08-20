"""Research Agent - Retrieves trusted references, collects style guidance, gathers asset candidates"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()


class ResearchResult(BaseModel):
    style_references: List[Dict[str, Any]] = []
    asset_candidates: List[Dict[str, Any]] = []
    constraints_summary: Dict[str, Any] = {}
    best_practices: List[str] = []


class ResearchAgent:
    """Retrieves reference materials and best practices for generation."""
    
    # Reference databases per domain
    STYLE_REFERENCES = {
        "real_estate": {
            "modern": [
                {"name": "Modern Minimalist", "source": "ArchDaily", "features": ["clean lines", "open plan", "neutral palette"]},
                {"name": "Scandinavian", "source": "Dezeen", "features": ["light wood", "white walls", "functional"]},
                {"name": "Industrial", "source": "ArchDaily", "features": ["exposed brick", "metal accents", "high ceilings"]},
                {"name": "Mid-Century Modern", "source": "Dwell", "features": ["organic shapes", "wood tones", "large windows"]},
            ],
            "traditional": [
                {"name": "Colonial", "source": "Traditional Home", "features": ["symmetrical", "columns", "shutters"]},
                {"name": "Victorian", "source": "Old House Journal", "features": ["ornate details", "bay windows", "steep roofs"]},
                {"name": "Mediterranean", "source": "Architectural Digest", "features": ["stucco", "tile roofs", "archways"]},
                {"name": "Craftsman", "source": "Fine Homebuilding", "features": ["exposed beams", "built-ins", "natural materials"]},
            ],
            "luxury": [
                {"name": "Contemporary Luxury", "source": "Robb Report", "features": ["smart home", "premium materials", "spa bathrooms"]},
                {"name": "Classic Luxury", "source": "Mansion Global", "features": ["marble", "crystal", "grand scale"]},
            ]
        },
        "heritage": {
            "temple": [
                {"name": "South Indian Temple", "source": "UNESCO", "features": ["gopuram", "mandapa", "sanctum", "pradakshina"]},
                {"name": "North Indian Temple", "source": "ASI", "features": ["shikhara", "mandapa", "garbhagriha"]},
                {"name": "Buddhist Temple", "source": "UNESCO", "features": ["stupa", "vihara", "chaitya"]},
            ],
            "palace": [
                {"name": "Mughal Palace", "source": "UNESCO", "features": ["diwan-i-am", "diwan-i-khas", "charbagh", "pietra dura"]},
                {"name": "Rajput Palace", "source": "ASI", "features": ["jharokha", "chhatri", "jaali", "courtyards"]},
                {"name": "European Palace", "source": "UNESCO", "features": ["grand staircase", "ballroom", "gardens", "fountains"]},
            ],
            "courtyard": [
                {"name": "Haveli Courtyard", "source": "INTACH", "features": ["chowk", "jali", "otla", "baradari"]},
                {"name": "Chinese Courtyard", "source": "UNESCO", "features": ["siheyuan", "screen wall", "roof tiles"]},
                {"name": "Islamic Courtyard", "source": "AKTC", "features": ["fountain", "arcades", "geometric patterns"]},
            ]
        }
    }
    
    # Best practices per domain
    BEST_PRACTICES = {
        "real_estate": [
            "Maintain clear sightlines from entry to key rooms",
            "Ensure minimum 36\" corridor width for comfortable navigation",
            "Place wet rooms (kitchen, bath) near plumbing stacks",
            "Orient living spaces toward best views/light",
            "Provide adequate storage in each bedroom",
            "Use consistent flooring transitions between rooms",
            "Layer lighting: ambient, task, accent in each space",
            "Consider furniture placement in room dimensions",
        ],
        "heritage": [
            "Respect historical accuracy in proportions and details",
            "Provide clear interpretive content at each POI",
            "Design circulation that follows historical visitor flow",
            "Use authentic materials and textures where possible",
            "Include multi-language narration support",
            "Preserve sightlines to key architectural features",
            "Balance educational content with exploration freedom",
            "Consider accessibility for diverse visitors",
        ]
    }
    
    # Asset candidate sources
    ASSET_SOURCES = {
        "models": [
            {"source": "Poly Haven", "license": "CC0", "quality": "high"},
            {"source": "Sketchfab", "license": "varied", "quality": "varied"},
            {"source": "Kenney.nl", "license": "CC0", "quality": "medium"},
            {"source": "Quaternius", "license": "CC0", "quality": "medium"},
        ],
        "textures": [
            {"source": "Poly Haven", "license": "CC0", "quality": "high"},
            {"source": "AmbientCG", "license": "CC0", "quality": "high"},
            {"source": "Texture Haven", "license": "CC0", "quality": "high"},
        ],
        "audio": [
            {"source": "Freesound", "license": "CC0/CC-BY", "quality": "varied"},
            {"source": "BBC Sound Effects", "license": "RemArc", "quality": "high"},
        ]
    }
    
    def research(self, domain: str, style: str, requirements: Dict[str, Any]) -> ResearchResult:
        """Gather research materials for generation."""
        
        # Get style references
        style_refs = self.STYLE_REFERENCES.get(domain, {}).get(style, [])
        if not style_refs:
            # Fallback to first available style
            available = self.STYLE_REFERENCES.get(domain, {})
            if available:
                style_refs = list(available.values())[0]
        
        # Get best practices
        practices = self.BEST_PRACTICES.get(domain, [])
        
        # Get asset sources
        asset_candidates = []
        for category, sources in self.ASSET_SOURCES.items():
            for source in sources:
                asset_candidates.append({
                    "category": category,
                    "source": source["source"],
                    "license": source["license"],
                    "quality": source["quality"]
                })
        
        # Constraints summary
        constraints = {
            "domain": domain,
            "style": style,
            "target_fps": requirements.get("target_fps", 60),
            "max_triangles": requirements.get("max_triangles", 100000),
            "texture_budget_mb": requirements.get("texture_budget_mb", 100),
            "platform": "mobile_vr",
            "rendering": "stereo_webrtc"
        }
        
        result = ResearchResult(
            style_references=style_refs,
            asset_candidates=asset_candidates,
            constraints_summary=constraints,
            best_practices=practices
        )
        
        logger.info("research_completed", domain=domain, style=style, refs=len(style_refs))
        return result
    
    def get_style_guidance(self, domain: str, style: str) -> Dict[str, Any]:
        """Get detailed style guidance for a specific style."""
        refs = self.STYLE_REFERENCES.get(domain, {}).get(style, [])
        
        if not refs:
            return {"error": f"Style '{style}' not found for domain '{domain}'"}
        
        # Aggregate features
        all_features = []
        for ref in refs:
            all_features.extend(ref.get("features", []))
        
        # Count feature frequency
        feature_counts = {}
        for f in all_features:
            feature_counts[f] = feature_counts.get(f, 0) + 1
        
        # Sort by frequency
        top_features = sorted(feature_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            "style": style,
            "domain": domain,
            "references": refs,
            "key_features": [f[0] for f in top_features],
            "feature_details": dict(top_features)
        }


# Global agent instance
research_agent = ResearchAgent()


def research_generation(domain: str, style: str, requirements: Dict[str, Any]) -> ResearchResult:
    """Convenience function for research."""
    return research_agent.research(domain, style, requirements)


def get_style_guidance(domain: str, style: str) -> Dict[str, Any]:
    """Convenience function for style guidance."""
    return research_agent.get_style_guidance(domain, style)