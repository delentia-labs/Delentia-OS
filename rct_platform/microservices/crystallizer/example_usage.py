"""
Example usage of ALGO-41: The Crystallizer

Demonstrates keyword extraction and concept expansion
"""

import asyncio
from crystallizer import Crystallizer


async def main():
    print("=" * 80)
    print("ALGO-41: The Crystallizer - Golden Keyword Extraction Demo")
    print("=" * 80)
    print()
    
    crystallizer = Crystallizer()
    
    # Example 1: Sovereignty-focused conversation
    print("Example 1: User asks about data sovereignty")
    print("-" * 80)
    
    conversation1 = """
    I want to build an app but I'm concerned about data sovereignty.
    I don't want to lose control over my users' data. Privacy is paramount.
    Can we use Next.js but self-host everything?
    """
    
    print(f"Input: {conversation1.strip()}")
    print()
    
    concept_maps = await crystallizer.crystallize(conversation1)
    
    print(f"✅ Detected {len(concept_maps)} golden keywords")
    print()
    
    for i, concept_map in enumerate(concept_maps, 1):
        keyword = concept_map.root_keyword
        print(f"Keyword {i}: '{keyword.word}'")
        print(f"  Category: {keyword.category.value}")
        print(f"  Entropy Score: {keyword.entropy_score:.2f}")
        print(f"  Context: ...{keyword.context}...")
        print()
        print(f"  Definition: {concept_map.definition}")
        print()
        
        if concept_map.expansion_nodes:
            print("  Related concepts:")
            for node in concept_map.expansion_nodes:
                print(f"    - {node.keyword}: {node.definition}")
        print()
        
        if concept_map.actionable_next_steps:
            print("  What you can do:")
            for action in concept_map.actionable_next_steps:
                print(f"    [{action['id']}] {action['label']}")
        print()
        
        print("  UI Schema:")
        print(f"    Type: {concept_map.ui_schema['type']}")
        print(f"    Sections: {len(concept_map.ui_schema['sections'])}")
        print()
    
    print("=" * 80)
    print()
    
    # Example 2: Technical stack conversation
    print("Example 2: User mentions specific technologies")
    print("-" * 80)
    
    conversation2 = """
    I'm thinking Next.js with PostgreSQL. 
    We need realtime updates for the inventory system.
    Performance and scalability are critical.
    """
    
    print(f"Input: {conversation2.strip()}")
    print()
    
    concept_maps = await crystallizer.crystallize(conversation2)
    
    print(f"✅ Detected {len(concept_maps)} golden keywords")
    print()
    
    for i, concept_map in enumerate(concept_maps, 1):
        keyword = concept_map.root_keyword
        print(f"Keyword {i}: '{keyword.word}'")
        print(f"  Category: {keyword.category.value}")
        print(f"  Entropy Score: {keyword.entropy_score:.2f}")
        print()
        
        if concept_map.expansion_nodes:
            print(f"  Expands to {len(concept_map.expansion_nodes)} related concepts:")
            for node in concept_map.expansion_nodes:
                print(f"    - {node.keyword}")
        print()
    
    print("=" * 80)
    print()
    
    # Example 3: Business domain conversation
    print("Example 3: Business logic keywords")
    print("-" * 80)
    
    conversation3 = """
    We need a payment system integrated with the inventory.
    Also need analytics dashboard and automated notifications.
    """
    
    print(f"Input: {conversation3.strip()}")
    print()
    
    concept_maps = await crystallizer.crystallize(conversation3)
    
    print(f"✅ Detected {len(concept_maps)} golden keywords")
    print()
    
    all_keywords = [cm.root_keyword for cm in concept_maps]
    print("All detected keywords:")
    for kw in all_keywords:
        print(f"  - {kw.word} ({kw.category.value}, score: {kw.entropy_score:.2f})")
    print()
    
    print("=" * 80)
    print()
    
    # Example 4: Integration with ITSR and Genesis
    print("Example 4: Full pipeline integration demo")
    print("-" * 80)
    
    conversation4 = "Build a realtime inventory system with sovereignty"
    
    print(f"Input: '{conversation4}'")
    print()
    
    # Step 1: Crystallizer extracts keywords
    concept_maps = await crystallizer.crystallize(conversation4)
    keywords = [cm.root_keyword.word for cm in concept_maps]
    
    print(f"Step 1 (Crystallizer): Extracted keywords: {keywords}")
    print()
    
    # Step 2: Pass to ITSR for tech stack recommendation
    print("Step 2 (ITSR): Would analyze requirements:")
    print("  - realtime: needs_realtime=True")
    print("  - sovereignty: self_hosted=True, open_source=True")
    print("  - inventory: business_domain='inventory'")
    print()
    
    print("Step 3 (Genesis): Would synthesize module based on:")
    print("  - Tech stack from ITSR")
    print("  - Concept maps from Crystallizer")
    print(f"  - Intent: {conversation4}")
    print()
    
    print("=" * 80)
    print()
    
    # Statistics
    stats = crystallizer.get_statistics()
    print("Crystallizer Statistics:")
    print(f"  Total concepts in knowledge base: {stats['total_concepts']}")
    print(f"  Entropy threshold: {stats['entropy_threshold']}")
    print(f"  Average expansion depth: {stats['average_expansion_depth']}")
    print(f"  Average crystallization time: {stats['average_crystallization_time']}")
    print()
    
    print("✅ All examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
