# Raw Seed → Blueprint → Search → Workspace：本轮实际记录

本文件由 summarize_pilot.py 从保存的结果生成。模型确实调用；没有搜索凭证，因此没有新文件或 ready Workspace。

| Seed | 职业 | Blueprint | 阻断环节 | Workspace / 搜索状态 |
|---|---|---|---|---|
| raw_31_0_13744 | Audiovisual Equipment Installers and Repairers | failed | graph_validation | not_run_blueprint_not_admitted / not_run |
| raw_31_0_16209 | Video Game Designers | failed | graph_validation | not_run_blueprint_not_admitted / not_run |
| raw_31_0_16425 | Automotive Engineers | accepted | — | incomplete / awaiting_search |
| raw_31_0_18983 | Computer Network Architects | failed | graph_validation | not_run_blueprint_not_admitted / not_run |
| raw_31_0_21094 | Regulatory Affairs Specialists | accepted | — | incomplete / not_started |
| raw_31_0_21676 | Software Developers | rejected | semantic_review | not_run_blueprint_not_admitted / not_run |
| raw_31_0_22125 | Surveying and Mapping Technicians | rejected | semantic_review | not_run_blueprint_not_admitted / not_run |
| raw_31_0_3405 | Budget Analysts | rejected | semantic_review | not_run_blueprint_not_admitted / not_run |
| raw_31_0_3747 | Biological Technicians | failed | graph_validation | not_run_blueprint_not_admitted / not_run |
| raw_31_0_871 | Construction and Building Inspectors | failed | graph_validation | not_run_blueprint_not_admitted / not_run |

## 三条完整处理记录

以下包含原始 Seed、完整模型输出、图边、审核和实际搜索记录。失败输出不是准入 Blueprint。

### raw_31_0_16425 · Automotive Engineers

```json
{
  "raw_seed": {
    "digital_label": "DIGITAL",
    "digital_label_source": "AI4Work",
    "dwa_ids": [
      "4.A.3.b.6.c.9",
      "4.A.3.b.6.h.21"
    ],
    "occupation_code": "17-2141.02",
    "occupation_title": "Automotive Engineers",
    "seed_id": "raw_31_0_16425",
    "source_metadata": {
      "date": "08/2022",
      "digital_annotation": {
        "annotation_row": "3584",
        "rule": "R1_DIGITAL"
      },
      "domain_source": "Occupational Expert",
      "row": 3576,
      "task_type": "Core"
    },
    "task_id": "16425",
    "task_source": "regular",
    "task_text": "Write, review, or maintain engineering documentation.",
    "work_domain": "Architecture and Engineering Occupations"
  },
  "blueprint": {
    "deliverables": [
      {
        "description": "A revised engineering document incorporating verified updates from engineering change notices and current design specifications, with tracked or summarized revisions for internal record-keeping.",
        "id": "Deliverable_UpdatedEngineeringDocument",
        "type": "document"
      }
    ],
    "dependencies": [
      [
        "I_ExistingEngineeringDocument",
        "D_IdentifiedDiscrepancies"
      ],
      [
        "I_EngineeringChangeNotices",
        "D_IdentifiedDiscrepancies"
      ],
      [
        "I_DesignSpecifications",
        "D_IdentifiedDiscrepancies"
      ],
      [
        "D_IdentifiedDiscrepancies",
        "D_RequiredDocumentRevisions"
      ],
      [
        "I_ExistingEngineeringDocument",
        "D_RequiredDocumentRevisions"
      ],
      [
        "D_RequiredDocumentRevisions",
        "J_RevisionCompleteness"
      ],
      [
        "J_RevisionCompleteness",
        "Deliverable_UpdatedEngineeringDocument"
      ]
    ],
    "information_nodes": [
      {
        "critical": true,
        "description": "The current draft or previously released engineering document that requires review and maintenance.",
        "id": "I_ExistingEngineeringDocument",
        "modality_candidates": [
          "text",
          "diagram"
        ],
        "modality_rationale": "Engineering documents routinely combine textual specifications with schematic diagrams; both may need to be read and updated.",
        "supply_channel": "workspace",
        "type": "external_input"
      },
      {
        "critical": true,
        "description": "Engineering change notices or revision requests describing modifications to be applied to the document.",
        "id": "I_EngineeringChangeNotices",
        "modality_candidates": [
          "text",
          "table"
        ],
        "modality_rationale": "Change notices are typically textual records that may include tabular lists of affected parameters or part numbers.",
        "supply_channel": "workspace",
        "type": "external_input"
      },
      {
        "critical": true,
        "description": "Current design specifications or technical data that define the correct parameters, tolerances, or configurations the document must reflect.",
        "id": "I_DesignSpecifications",
        "modality_candidates": [
          "text",
          "table"
        ],
        "modality_rationale": "Design specifications are commonly maintained as structured text with tabular parameter data.",
        "supply_channel": "workspace",
        "type": "external_input"
      },
      {
        "description": "Discrepancies between the existing engineering document and the current design specifications or engineering change notices.",
        "id": "D_IdentifiedDiscrepancies",
        "type": "derived_information"
      },
      {
        "description": "Specific textual and diagrammatic revisions needed to bring the engineering document into alignment with current specifications and change notices.",
        "id": "D_RequiredDocumentRevisions",
        "type": "derived_information"
      },
      {
        "description": "Judgment that all necessary revisions have been identified and that the updated document is complete, internally consistent, and suitable for internal release.",
        "id": "J_RevisionCompleteness",
        "type": "professional_judgment"
      }
    ],
    "modality_hypotheses": [
      {
        "evidence_status": "unretrieved",
        "information_needed": "Schematic diagrams or engineering drawings embedded in the document that must be visually interpreted to verify that depicted components, connections, and configurations match current specifications.",
        "modality_candidate": "diagram",
        "modality_rationale": "Automotive engineering documents frequently include diagrams whose correctness cannot be assessed through text alone; the spatial relationships and component representations must be visually inspected.",
        "necessity_status": "hypothesis",
        "node_id": "I_ExistingEngineeringDocument"
      }
    ],
    "seed_id": "raw_31_0_16425",
    "work_objective": "Review and update an existing automotive engineering document so that it accurately reflects current design specifications and engineering change decisions, producing a maintained revision suitable for internal use."
  },
  "deterministic_checks": {
    "all_nodes_serve_outputs": true,
    "dag": true,
    "modality_linkage": true,
    "roots_and_sinks": true,
    "schema": true,
    "seed_id": true
  },
  "semantic_review": {
    "accepted": true,
    "checks": {
      "case_neutrality": true,
      "deliverable_validity": true,
      "dependency_correctness": true,
      "information_sufficiency": true,
      "intent_preservation": true,
      "minimality": true,
      "multimodal_justification": true
    },
    "issues": []
  },
  "planning_status": "accepted",
  "planning_failures": [],
  "search_trace": {
    "events": [
      {
        "provider": "tavily",
        "query": "automotive engineering change notice ECN service manual revision procedure example",
        "reason": "missing_search_api_credentials",
        "results": [],
        "search_api_called": false,
        "status": "awaiting_search"
      }
    ],
    "mode": "graph",
    "rounds": [
      {
        "retrieval_plan": {
          "queries": [
            {
              "desired_source_type": "publicly available engineering change notice and corresponding manual revision from an original equipment manufacturer or engineering standards body",
              "query": "automotive engineering change notice ECN service manual revision procedure example",
              "reason": "Need a coherent real-world anchor that pairs an existing engineering document with formal change notices so both critical input nodes can be satisfied within a single organization and project.",
              "target_node_ids": [
                "I_EngineeringChangeNotices",
                "I_ExistingEngineeringDocument"
              ]
            },
            {
              "desired_source_type": "manufacturer documentation set containing original document, revision bulletin, and current design specification",
              "query": "OEM technical service bulletin and workshop manual revision history automotive component specification update",
              "reason": "Locate a reusable documentation set where the pre-revision document, change instruction, and current specification coexist, supporting all three critical nodes and the diagram modality hypothesis.",
              "target_node_ids": [
                "I_ExistingEngineeringDocument",
                "I_DesignSpecifications",
                "I_EngineeringChangeNotices"
              ]
            },
            {
              "desired_source_type": "native engineering drawing or schematic with accompanying revision description, preferably in its original diagram format",
              "query": "automotive wiring diagram or assembly drawing revision from change request to updated schematic",
              "reason": "The blueprint requires visual verification of depicted components and connections; a native drawing with revision context provides evidence that cannot be substituted by text descriptions.",
              "target_node_ids": [
                "I_ExistingEngineeringDocument",
                "I_DesignSpecifications"
              ]
            },
            {
              "desired_source_type": "authoritative design specification or technical data sheet with tabular parameters and tolerances",
              "query": "public automotive engineering specification document with parameter table and tolerance values for component configuration",
              "reason": "Design specifications are a critical node requiring correct parameters and tolerances; a primary specification with tabular data supports discrepancy identification and revision planning.",
              "target_node_ids": [
                "I_DesignSpecifications"
              ]
            },
            {
              "desired_source_type": "documented configuration management or revision control record from a public engineering program",
              "query": "NASA or SAE engineering document revision control case study with configuration management records",
              "reason": "Alternative anchor candidate where revision-controlled engineering documents, change requests, and current specifications are publicly archived together, preserving project and time-period consistency.",
              "target_node_ids": [
                "I_ExistingEngineeringDocument",
                "I_EngineeringChangeNotices",
                "I_DesignSpecifications"
              ]
            }
          ],
          "stop_reason": null,
          "strategy": "anchor_search"
        },
        "round": 0
      }
    ]
  },
  "workspace": {
    "workspace_id": "WS_3ff8d749c6f4",
    "status": "incomplete",
    "search_state": "awaiting_search",
    "selected_anchor": null,
    "counts": {
      "actual_search_requests": 0,
      "critical_coverage": 0.0,
      "critical_external_nodes": 3,
      "download_attempts": 0,
      "download_or_profile_failures": 0,
      "downloaded_urls": 0,
      "duplicate_files": 0,
      "independently_verified_visual_evidence": 0,
      "parsed_unique_files": 0,
      "planned_queries": 5,
      "retained_files": 0,
      "supported_critical_nodes": 0,
      "synthetic_files": 0
    },
    "missing_nodes": [
      "I_ExistingEngineeringDocument",
      "I_EngineeringChangeNotices",
      "I_DesignSpecifications"
    ],
    "failure_reasons": [
      {
        "reason": "awaiting_search: configure a real Search API key; no autonomous search executed",
        "stage": "search"
      },
      {
        "reason": "no_grounded_anchor",
        "stage": "anchor_discovery"
      }
    ],
    "modality_evidence": [
      {
        "evidence_status": "unretrieved",
        "independently_verified": false,
        "information_needed": "Schematic diagrams or engineering drawings embedded in the document that must be visually interpreted to verify that depicted components, connections, and configurations match current specifications.",
        "modality_candidate": "diagram",
        "modality_rationale": "Automotive engineering documents frequently include diagrams whose correctness cannot be assessed through text alone; the spatial relationships and component representations must be visually inspected.",
        "necessity_status": "hypothesis",
        "node_id": "I_ExistingEngineeringDocument"
      }
    ]
  }
}
```

### raw_31_0_21094 · Regulatory Affairs Specialists

```json
{
  "raw_seed": {
    "digital_label": "DIGITAL",
    "digital_label_source": "AI4Work",
    "dwa_ids": [
      "4.A.2.a.2.c.2",
      "4.A.2.a.3.a.4",
      "4.A.2.a.4.i.4"
    ],
    "occupation_code": "13-1041.07",
    "occupation_title": "Regulatory Affairs Specialists",
    "seed_id": "raw_31_0_21094",
    "source_metadata": {
      "date": "08/2026",
      "digital_annotation": {
        "annotation_row": "1421",
        "rule": "R1_DIGITAL"
      },
      "domain_source": "Occupational Expert",
      "row": 1413,
      "task_type": "Core"
    },
    "task_id": "21094",
    "task_source": "regular",
    "task_text": "Identify relevant guidance documents, international standards, or consensus standards.",
    "work_domain": "Business and Financial Operations Occupations"
  },
  "blueprint": {
    "deliverables": [
      {
        "description": "A structured list of the guidance documents, international standards, and consensus standards identified as relevant, with each source named, its issuing body noted, and its applicability to the situation stated.",
        "id": "d1",
        "type": "Curated standards and guidance reference list"
      }
    ],
    "dependencies": [
      [
        "i1",
        "i4"
      ],
      [
        "i2",
        "i4"
      ],
      [
        "i1",
        "i5"
      ],
      [
        "i4",
        "i6"
      ],
      [
        "i5",
        "i6"
      ],
      [
        "i3",
        "i6"
      ],
      [
        "i6",
        "i7"
      ],
      [
        "i7",
        "i8"
      ],
      [
        "i8",
        "d1"
      ]
    ],
    "information_nodes": [
      {
        "critical": true,
        "description": "The regulatory context defining the subject area, product or activity in scope, and any applicable jurisdictions or markets.",
        "id": "i1",
        "modality_candidates": [
          "text"
        ],
        "modality_rationale": "Scope and context are conveyed as written narrative in the request.",
        "supply_channel": "task_instruction",
        "type": "external_input"
      },
      {
        "critical": true,
        "description": "Internal or workspace source materials describing the organization's product, process, or activity that the standards must apply to.",
        "id": "i2",
        "modality_candidates": [
          "text",
          "table"
        ],
        "modality_rationale": "Technical descriptions and specification tables typically document the product or activity.",
        "supply_channel": "workspace",
        "type": "external_input"
      },
      {
        "critical": true,
        "description": "Reference sources listing guidance documents, international standards, and consensus standards, including titles, issuing bodies, and scope statements.",
        "id": "i3",
        "modality_candidates": [
          "text",
          "table"
        ],
        "modality_rationale": "Standards catalogs and registers present titles and scope information as text and tabular metadata.",
        "supply_channel": "external_reference",
        "type": "external_input"
      },
      {
        "description": "The technical subject matter and criteria of the organization's product or activity that determine which categories of standards apply.",
        "id": "i4",
        "type": "derived_information"
      },
      {
        "description": "The jurisdictions and regulatory domains that govern the activity and therefore constrain which standards are relevant.",
        "id": "i5",
        "type": "derived_information"
      },
      {
        "description": "A mapping of candidate standards and guidance documents to the derived subject matter and jurisdictional criteria, showing where each candidate matches or fails to match.",
        "id": "i6",
        "type": "derived_information"
      },
      {
        "description": "Determination of which candidate standards and guidance documents are relevant and applicable to the regulatory situation, with justification for inclusions and exclusions.",
        "id": "i7",
        "type": "professional_judgment"
      },
      {
        "description": "For each selected source, the specific applicability rationale linking the standard's scope to the organization's activity and governing requirements.",
        "id": "i8",
        "type": "derived_information"
      }
    ],
    "modality_hypotheses": [],
    "seed_id": "raw_31_0_21094",
    "work_objective": "Identify the guidance documents, international standards, and consensus standards relevant to a given regulatory situation, and produce a curated reference list documenting each identified source and its relevance."
  },
  "deterministic_checks": {
    "all_nodes_serve_outputs": true,
    "dag": true,
    "modality_linkage": true,
    "roots_and_sinks": true,
    "schema": true,
    "seed_id": true
  },
  "semantic_review": {
    "accepted": true,
    "checks": {
      "case_neutrality": true,
      "deliverable_validity": true,
      "dependency_correctness": true,
      "information_sufficiency": true,
      "intent_preservation": true,
      "minimality": true,
      "multimodal_justification": true
    },
    "issues": []
  },
  "planning_status": "accepted",
  "planning_failures": [],
  "search_trace": {
    "events": [],
    "mode": "graph",
    "rounds": [
      {
        "event": "invalid_retrieval_plan",
        "proposed_retrieval_plan": {
          "queries": [
            {
              "desired_source_type": "workspace technical file, product specification sheet, or process description from a real organization",
              "query": "regulatory affairs product technical file specification example medical device or chemical product compliance documentation",
              "reason": "No anchor exists yet; i2 is a critical missing workspace node. Need a real organization's product/process documentation to ground which standards categories apply.",
              "target_node_ids": [
                "i2"
              ]
            },
            {
              "desired_source_type": "standards register, catalog, or official standards body equivalence listing (e.g., ISO, IEC, national body indexes)",
              "query": "standards catalog listing ISO IEC consensus standards titles issuing bodies scope statements regulatory affairs",
              "reason": "i3 is the other critical missing node; the deliverable requires named sources with issuing bodies and scope, so a real catalog/register is needed as the reference anchor.",
              "target_node_ids": [
                "i3"
              ]
            },
            {
              "desired_source_type": "issuing body guidance page or cross-reference index linking standards to regulatory domains",
              "query": "ISO IEC regulatory affairs standards mapping product scope jurisdiction applicability guidance document",
              "reason": "Supports building the standards-to-subject/jurisdiction mapping (i6) while reinforcing the i3 reference anchor with real issuing-body metadata.",
              "target_node_ids": [
                "i3",
                "i6"
              ]
            },
            {
              "desired_source_type": "professional practice guide or case example of standards applicability determination",
              "query": "regulatory affairs specialist curated reference list standards applicability justification example",
              "reason": "Anchor discovery step: identify a coherent real case showing both the organization context and the standards set used, so later gap-filling stays within one compatible project.",
              "target_node_ids": [
                "i2",
                "i3"
              ]
            },
            {
              "desired_source_type": "standards body overview or scope register covering multiple jurisdictions",
              "query": "international consensus standards scope statement issuing body jurisdiction market application regulatory framework overview",
              "reason": "Broadens the i3 candidate pool with authoritative scope statements, ensuring the eventual curated list can be verified against named issuing bodies rather than title matches.",
              "target_node_ids": [
                "i3"
              ]
            }
          ],
          "stop_reason": null,
          "strategy": "anchor_search"
        },
        "round": 0
      }
    ]
  },
  "workspace": {
    "workspace_id": "WS_97f914e6ade5",
    "status": "incomplete",
    "search_state": "not_started",
    "selected_anchor": null,
    "counts": {
      "actual_search_requests": 0,
      "critical_coverage": 0.0,
      "critical_external_nodes": 2,
      "download_attempts": 0,
      "download_or_profile_failures": 0,
      "downloaded_urls": 0,
      "duplicate_files": 0,
      "independently_verified_visual_evidence": 0,
      "parsed_unique_files": 0,
      "planned_queries": 0,
      "retained_files": 0,
      "supported_critical_nodes": 0,
      "synthetic_files": 0
    },
    "missing_nodes": [
      "i2",
      "i3"
    ],
    "failure_reasons": [
      {
        "reason": "query_targets_non_retrievable_node",
        "stage": "retrieval_planning"
      },
      {
        "reason": "no_grounded_anchor",
        "stage": "anchor_discovery"
      }
    ],
    "modality_evidence": []
  }
}
```

### raw_31_0_871 · Construction and Building Inspectors

```json
{
  "raw_seed": {
    "digital_label": "DIGITAL",
    "digital_label_source": "AI4Work",
    "dwa_ids": [
      "4.A.1.a.1.b.9",
      "4.A.1.a.2.k.9"
    ],
    "occupation_code": "47-4011.00",
    "occupation_title": "Construction and Building Inspectors",
    "seed_id": "raw_31_0_871",
    "source_metadata": {
      "date": "08/2024",
      "digital_annotation": {
        "annotation_row": "14342",
        "rule": "R1_DIGITAL"
      },
      "domain_source": "Occupational Expert",
      "row": 14356,
      "task_type": "Core"
    },
    "task_id": "871",
    "task_source": "regular",
    "task_text": "Review and interpret plans, blueprints, site layouts, specifications, or construction methods to ensure compliance to legal requirements and safety regulations.",
    "work_domain": "Construction and Extraction Occupations"
  },
  "blueprint": {
    "deliverables": [
      {
        "description": "A documented review identifying where the plans, layouts, specifications, and construction methods conform to or conflict with applicable legal requirements and safety regulations, with references to the specific document features examined.",
        "id": "d1",
        "type": "compliance review report"
      }
    ],
    "dependencies": [
      [
        "i1",
        "i7"
      ],
      [
        "i2",
        "i7"
      ],
      [
        "i3",
        "i7"
      ],
      [
        "i4",
        "i6"
      ],
      [
        "i6",
        "i8"
      ],
      [
        "i7",
        "i8"
      ],
      [
        "i5",
        "i9"
      ],
      [
        "i6",
        "i9"
      ],
      [
        "i8",
        "d1"
      ],
      [
        "i9",
        "d1"
      ]
    ],
    "information_nodes": [
      {
        "critical": true,
        "description": "The project's plans and blueprints showing building layout, dimensions, structural elements, and design intent.",
        "id": "i1",
        "modality_candidates": [
          "text",
          "image",
          "diagram",
          "spatial"
        ],
        "modality_rationale": "Plans and blueprints are typically graphic drawings where spatial arrangement, dimensions, and symbols carry meaning.",
        "supply_channel": "workspace",
        "type": "external_input"
      },
      {
        "critical": true,
        "description": "Site layout drawings showing the placement of structures, access, and site conditions relative to the project.",
        "id": "i2",
        "modality_candidates": [
          "image",
          "diagram",
          "spatial"
        ],
        "modality_rationale": "Site layouts are spatial drawings where relative positioning and distances must be read visually.",
        "supply_channel": "workspace",
        "type": "external_input"
      },
      {
        "critical": true,
        "description": "Written specifications stating materials, methods, and performance requirements for the project.",
        "id": "i3",
        "modality_candidates": [
          "text",
          "table"
        ],
        "modality_rationale": "Specifications are conveyed as text, often with tabulated requirements.",
        "supply_channel": "workspace",
        "type": "external_input"
      },
      {
        "critical": true,
        "description": "The applicable legal requirements and safety regulations that govern the project, including the specific provisions relevant to the project type.",
        "id": "i4",
        "modality_candidates": [
          "text"
        ],
        "modality_rationale": "Regulatory requirements are codified in textual code and regulation documents.",
        "supply_channel": "external_reference",
        "type": "external_input"
      },
      {
        "critical": false,
        "description": "The construction methods proposed for the project, such as sequencing and execution approaches described for the work.",
        "id": "i5",
        "modality_candidates": [
          "text"
        ],
        "modality_rationale": "Construction methods are described in narrative or procedural text.",
        "supply_channel": "workspace",
        "type": "external_input"
      },
      {
        "description": "The governing requirements from the applicable regulations that specifically apply to this project type and its features.",
        "id": "i6",
        "type": "derived_information",
        "type_note": null
      },
      {
        "description": "The design parameters and performance conditions stated in the plans, layouts, and specifications relevant to those governing requirements.",
        "id": "i7",
        "type": "derived_information"
      },
      {
        "description": "The determination of where the plans, layouts, specifications, and construction methods conform to or conflict with the governing legal and safety requirements, and the significance of any conflicts.",
        "id": "i8",
        "type": "professional_judgment"
      },
      {
        "description": "The determination of whether proposed construction methods introduce safety-regulation noncompliance not evident from the design documents alone.",
        "id": "i9",
        "type": "professional_judgment"
      }
    ],
    "modality_hypotheses": [
      {
        "evidence_status": "unretrieved",
        "information_needed": "Layout, dimensions, and structural annotations shown in the blueprints.",
        "modality_candidate": "image",
        "modality_rationale": "Blueprints are graphical drawings whose meaning depends on visual interpretation of geometry and symbols.",
        "necessity_status": "hypothesis",
        "node_id": "i1"
      },
      {
        "evidence_status": "unretrieved",
        "information_needed": "Relative placement of structures, access, and site features requiring spatial interpretation.",
        "modality_candidate": "spatial",
        "modality_rationale": "Site layouts convey spatial relationships and distances that cannot be fully captured in text.",
        "necessity_status": "hypothesis",
        "node_id": "i2"
      }
    ],
    "seed_id": "raw_31_0_871",
    "work_objective": "Review and interpret a construction project's plans, blueprints, site layouts, specifications, and construction methods to determine whether the design complies with applicable legal requirements and safety regulations, and produce a documented compliance review."
  },
  "deterministic_checks": null,
  "semantic_review": null,
  "planning_status": "failed",
  "planning_failures": [
    "schema:['information_nodes', 5]: {'id': 'i6', 'type': 'derived_information', 'description': 'The governing requirements from the applicable regulations that specifically apply to this project type and its features.', 'type_note': Non"
  ],
  "search_trace": {
    "status": "not_run",
    "reason": "blueprint_not_admitted"
  },
  "workspace": {
    "status": "not_constructed"
  }
}
```

## 实际目录

```text
workspaces/data/generated/WS_3ff8d749c6f4/
├── workspace_init/                 # 空；尚未获取真实输入文件
└── construction/
    ├── search_trace.json
    ├── source_manifest.json         # sources 为空
    ├── file_profiles.json           # 空
    ├── information_coverage.json    # 三个关键节点均 missing
    └── construction_report.json     # incomplete / awaiting_search
```

没有可展示的新来源。两份历史 CSV/XLSX 的真实来源、哈希及定位回归见 regression_report.json；它们不构成本轮 Workspace。
