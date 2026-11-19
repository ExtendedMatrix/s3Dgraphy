.. _types:

Types — nodes and edges
=======================

.. note::

   Generated from the datamodels (nodes 1.6.51, connections 1.6.55) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

The types of the EM language: what ``em.graph`` returns as :class:`~s3dgraphy.em.NodeView` and :class:`~s3dgraphy.em.EdgeView`, and what ``tx.add_node`` / ``tx.add_edge`` accept. The edges a node may have are checked by the contract at every write.

Node types
----------

.. list-table::
   :header-rows: 1
   :widths: 30 15 30 25

   * - Class
     - node_type
     - Label
     - Etichetta (it)
   * - :ref:`ActivityNodeGroup <type-ActivityNodeGroup>`
     - ``ActivityNodeGroup``
     - Activity Node Group
     - Gruppo di attività
   * - :ref:`AnnotationRegionNode <type-AnnotationRegionNode>`
     - ``annotation_region``
     - Annotation Region
     - Regione di annotazione
   * - :ref:`AuthorAINode <type-AuthorAINode>`
     - ``author_ai``
     - AI Author
     - Autore IA
   * - :ref:`AuthorNode <type-AuthorNode>`
     - ``author``
     - Author (human)
     - Autore (umano)
   * - :ref:`CombinerNode <type-CombinerNode>`
     - ``combiner``
     - Combiner
     - Combinatore
   * - :ref:`ContinuityNode <type-ContinuityNode>`
     - ``BR``
     - continuity node
     - Nodo di continuità
   * - :ref:`DTCAcquisitionNode <type-DTCAcquisitionNode>`
     - ``dtc_acquisition``
     - DTC Acquisition
     - Acquisizione DTC
   * - :ref:`DTCDeviceNode <type-DTCDeviceNode>`
     - ``dtc_device``
     - DTC Device
     - Dispositivo DTC
   * - :ref:`DTCNode <type-DTCNode>`
     - —
     - DTCNode
     - —
   * - :ref:`DTCProcessNode <type-DTCProcessNode>`
     - ``dtc_process``
     - DTC Process
     - Processo DTC
   * - :ref:`DistrictNode <type-DistrictNode>`
     - ``district``
     - District
     - Distretto
   * - :ref:`DocumentNode <type-DocumentNode>`
     - ``document``
     - Document
     - Documento
   * - :ref:`DocumentaryStratigraphicUnit <type-DocumentaryStratigraphicUnit>`
     - ``USD``
     - USD
     - USD
   * - :ref:`EmbargoNode <type-EmbargoNode>`
     - ``embargo``
     - Embargo
     - Embargo
   * - :ref:`EpochNode <type-EpochNode>`
     - ``EpochNode``
     - Epoch
     - Epoca
   * - :ref:`ExtractorNode <type-ExtractorNode>`
     - ``extractor``
     - Extractor
     - Estrattore
   * - :ref:`FunctionalUnitNodeGroup <type-FunctionalUnitNodeGroup>`
     - ``FunctionalUnitNodeGroup``
     - Functional Unit
     - Unità funzionale
   * - :ref:`GCPSetNode <type-GCPSetNode>`
     - ``gcp_set``
     - Ground control points
     - Punti di controllo a terra
   * - :ref:`GeoPositionNode <type-GeoPositionNode>`
     - ``geo_position``
     - Geo Position
     - Posizione geografica
   * - :ref:`GraphNode <type-GraphNode>`
     - ``graph``
     - Graph
     - Grafo
   * - :ref:`GroupNode <type-GroupNode>`
     - ``Group``
     - GroupNode
     - —
   * - :ref:`HDTNode <type-HDTNode>`
     - ``hdt``
     - Heritage Digital Twin
     - Gemello digitale del patrimonio
   * - :ref:`HeritageEntityNode <type-HeritageEntityNode>`
     - ``heritage_entity``
     - Heritage Entity
     - Entità patrimoniale
   * - :ref:`HorizonNode <type-HorizonNode>`
     - ``horizon``
     - Horizon
     - Orizzonte
   * - :ref:`LandscapeSurfaceNode <type-LandscapeSurfaceNode>`
     - ``landscape_surface``
     - Landscape surface
     - Superficie del paesaggio
   * - :ref:`LandscapeUnitNode <type-LandscapeUnitNode>`
     - —
     - LandscapeUnitNode
     - —
   * - :ref:`LicenseNode <type-LicenseNode>`
     - ``license``
     - License
     - Licenza
   * - :ref:`LocationNodeGroup <type-LocationNodeGroup>`
     - ``LocationNodeGroup``
     - Location Node Group
     - Gruppo di luogo
   * - :ref:`NarrativeNode <type-NarrativeNode>`
     - ``narrative``
     - Narrative
     - Narrazione
   * - :ref:`NegativeStratigraphicUnit <type-NegativeStratigraphicUnit>`
     - ``USN``
     - US-
     - US-
   * - :ref:`NegativeTopographicUnitNode <type-NegativeTopographicUnitNode>`
     - ``UT0``
     - −UT
     - −UT
   * - :ref:`NeutralStratigraphicUnit <type-NeutralStratigraphicUnit>`
     - ``USNt``
     - USNt
     - USNt
   * - :ref:`Node <type-Node>`
     - ``Node``
     - Node
     - —
   * - :ref:`NonStructuralVirtualStratigraphicUnit <type-NonStructuralVirtualStratigraphicUnit>`
     - ``USVn``
     - USV/n
     - USV/n
   * - :ref:`ParadataNode <type-ParadataNode>`
     - ``ParadataNode``
     - ParadataNode
     - —
   * - :ref:`ParadataNodeGroup <type-ParadataNodeGroup>`
     - ``ParadataNodeGroup``
     - Paradata Node Group
     - Gruppo di paradati
   * - :ref:`PeriodizationNode <type-PeriodizationNode>`
     - ``periodization``
     - Periodization
     - Periodizzazione
   * - :ref:`ProjectNode <type-ProjectNode>`
     - ``project``
     - Project
     - Progetto
   * - :ref:`PropertyNode <type-PropertyNode>`
     - ``property``
     - Property
     - Proprietà
   * - :ref:`RegistrationTransformNode <type-RegistrationTransformNode>`
     - ``registration_transform``
     - Registration transform
     - Trasformazione di registrazione
   * - :ref:`RepresentationModelDocNode <type-RepresentationModelDocNode>`
     - ``representation_model_doc``
     - Representation Model Document
     - Modello di rappresentazione di documento
   * - :ref:`RepresentationModelNode <type-RepresentationModelNode>`
     - ``representation_model``
     - Representation Model
     - Modello di rappresentazione
   * - :ref:`RepresentationModelNodeGroup <type-RepresentationModelNodeGroup>`
     - ``RepresentationModelNodeGroup``
     - RM Container
     - Contenitore RM
   * - :ref:`RepresentationModelSpecialFindNode <type-RepresentationModelSpecialFindNode>`
     - ``representation_model_sf``
     - Representation Model Special Find
     - Modello di rappresentazione di reperto
   * - :ref:`RepresentationNode <type-RepresentationNode>`
     - —
     - RepresentationNode
     - —
   * - :ref:`ResourceFileNode <type-ResourceFileNode>`
     - ``resource_file``
     - Resource file
     - File della risorsa
   * - :ref:`ResourceNode <type-ResourceNode>`
     - ``resource``
     - Link
     - Collegamento
   * - :ref:`ReusedSpecialFind <type-ReusedSpecialFind>`
     - ``RSF``
     - Repositioned Special Find
     - Reperto speciale riposizionato
   * - :ref:`SemanticShapeNode <type-SemanticShapeNode>`
     - ``semantic_shape``
     - Semantic Shape
     - Forma semantica
   * - :ref:`SeriesOfDocumentaryStratigraphicUnit <type-SeriesOfDocumentaryStratigraphicUnit>`
     - ``serUSD``
     - USD series
     - Serie di USD
   * - :ref:`SeriesOfNonStructuralVirtualStratigraphicUnit <type-SeriesOfNonStructuralVirtualStratigraphicUnit>`
     - ``serUSVn``
     - USVn series
     - Serie di USVn
   * - :ref:`SeriesOfStratigraphicUnit <type-SeriesOfStratigraphicUnit>`
     - ``serSU``
     - US series
     - Serie di US
   * - :ref:`SeriesOfStructuralVirtualStratigraphicUnit <type-SeriesOfStructuralVirtualStratigraphicUnit>`
     - ``serUSVs``
     - USVs series
     - Serie di USVs
   * - :ref:`SeriesOfVirtualSpecialFindUnit <type-SeriesOfVirtualSpecialFindUnit>`
     - ``serVSF``
     - VSF series
     - Serie di VSF
   * - :ref:`SpecialFindUnit <type-SpecialFindUnit>`
     - ``SF``
     - Special Find
     - Reperto speciale
   * - :ref:`StratigraphicEventNode <type-StratigraphicEventNode>`
     - ``SE``
     - stratigraphic event node
     - Evento stratigrafico
   * - :ref:`StratigraphicNode <type-StratigraphicNode>`
     - ``StratigraphicNode``
     - StratigraphicNode
     - —
   * - :ref:`StratigraphicUnit <type-StratigraphicUnit>`
     - ``US``
     - US (or SU)
     - US (o UStr)
   * - :ref:`StructuralVirtualStratigraphicUnit <type-StructuralVirtualStratigraphicUnit>`
     - ``USVs``
     - USV/s
     - USV/s
   * - :ref:`StudyNode <type-StudyNode>`
     - ``study``
     - Study
     - Studio
   * - :ref:`TimeBranchNodeGroup <type-TimeBranchNodeGroup>`
     - ``TimeBranchNodeGroup``
     - Time Branch Node Group
     - Gruppo di ramo temporale
   * - :ref:`TopographicUnitNode <type-TopographicUnitNode>`
     - ``UT``
     - UT
     - UT
   * - :ref:`TransformationStratigraphicUnit <type-TransformationStratigraphicUnit>`
     - ``TSU``
     - TSU
     - TSU
   * - :ref:`TranslationNode <type-TranslationNode>`
     - ``translation``
     - Translation
     - Traduzione
   * - :ref:`UnknownNode <type-UnknownNode>`
     - ``unknown``
     - Unknown node
     - Nodo sconosciuto
   * - :ref:`VirtualSpecialFindUnit <type-VirtualSpecialFindUnit>`
     - ``VSF``
     - Virtual Special Find
     - Reperto speciale virtuale
   * - :ref:`VirtualStratigraphicUnit <type-VirtualStratigraphicUnit>`
     - —
     - VirtualStratigraphicUnit
     - —
   * - :ref:`WorkingUnit <type-WorkingUnit>`
     - ``UL``
     - UL
     - UL

Edge types
----------

.. list-table::
   :header-rows: 1
   :widths: 30 25 25 20

   * - Edge
     - Label
     - Etichetta (it)
     - Reverse
   * - :ref:`abuts <edge-abuts>`
     - Abuts
     - Si appoggia a
     - ``is_abutted_by``
   * - :ref:`bonded_to <edge-bonded_to>`
     - Bonded to
     - In legame con
     - —
   * - :ref:`changed_from <edge-changed_from>`
     - Changed from
     - Trasformato da
     - ``changed_to``
   * - :ref:`combines <edge-combines>`
     - Combines
     - Combina
     - ``is_combined_by``
   * - :ref:`contains_proposition_set <edge-contains_proposition_set>`
     - Contains proposition set
     - Contiene insieme di proposizioni
     - ``is_proposition_set_of``
   * - :ref:`contrasts_with <edge-contrasts_with>`
     - Contrasts with
     - In contrasto con
     - —
   * - :ref:`cuts <edge-cuts>`
     - Cuts
     - Taglia
     - ``is_cut_by``
   * - :ref:`dtc_derived_from <edge-dtc_derived_from>`
     - DTC output derived from input
     - L'uscita DTC deriva dall'ingresso
     - ``dtc_derivation_source_for``
   * - :ref:`dtc_had_input <edge-dtc_had_input>`
     - DTC process had input
     - Il processo DTC ha avuto in ingresso
     - ``dtc_was_input_of``
   * - :ref:`dtc_had_output <edge-dtc_had_output>`
     - DTC process had output
     - Il processo DTC ha avuto in uscita
     - ``dtc_was_output_of``
   * - :ref:`dtc_happened_on_device <edge-dtc_happened_on_device>`
     - Happened on device
     - Avvenuto sul dispositivo
     - ``dtc_was_device_of``
   * - :ref:`equals <edge-equals>`
     - Equals
     - Uguale a
     - —
   * - :ref:`extracted_from <edge-extracted_from>`
     - Extracted from
     - Estratto da
     - ``is_source_for_extraction``
   * - :ref:`fills <edge-fills>`
     - Fills
     - Riempie
     - ``is_filled_by``
   * - :ref:`generic_connection <edge-generic_connection>`
     - Generic connection
     - Connessione generica
     - —
   * - :ref:`has_author <edge-has_author>`
     - Has author
     - Ha autore
     - ``is_author_of``
   * - :ref:`has_data_provenance <edge-has_data_provenance>`
     - Has data provenance
     - Ha provenienza del dato
     - ``is_data_provenance_of``
   * - :ref:`has_digital_object_part <edge-has_digital_object_part>`
     - Has digital object part
     - Ha parte di oggetto digitale
     - ``is_digital_object_part_of``
   * - :ref:`has_digital_twin <edge-has_digital_twin>`
     - Has digital twin
     - Ha gemello digitale
     - ``is_digital_twin_of``
   * - :ref:`has_digital_twin_component <edge-has_digital_twin_component>`
     - Has digital twin component
     - Ha componente del gemello digitale
     - ``is_digital_twin_component_of``
   * - :ref:`has_documentation <edge-has_documentation>`
     - Has documentation
     - Ha documentazione
     - ``is_documentation_of``
   * - :ref:`has_embargo <edge-has_embargo>`
     - Has embargo
     - Ha embargo
     - ``is_embargo_of``
   * - :ref:`has_file <edge-has_file>`
     - Has file
     - Ha il file
     - ``is_file_of``
   * - :ref:`has_first_epoch <edge-has_first_epoch>`
     - Has first epoch
     - Ha come prima epoca
     - ``is_first_epoch_of``
   * - :ref:`has_gcp_set <edge-has_gcp_set>`
     - Solved from control points
     - Risolto da punti di controllo
     - ``controlled_registration``
   * - :ref:`has_geoposition <edge-has_geoposition>`
     - Has geoposition
     - Ha posizione geografica
     - ``is_geoposition_of``
   * - :ref:`has_license <edge-has_license>`
     - Has license
     - Ha licenza
     - ``is_license_of``
   * - :ref:`has_linked_resource <edge-has_linked_resource>`
     - Has linked resource
     - Ha collegamento
     - ``is_linked_resource_of``
   * - :ref:`has_paradata_nodegroup <edge-has_paradata_nodegroup>`
     - Has paradata nodegroup
     - Ha gruppo di paradati
     - ``is_paradata_nodegroup_of``
   * - :ref:`has_property <edge-has_property>`
     - Has property
     - Ha la proprietà
     - ``is_property_of``
   * - :ref:`has_registration_transform <edge-has_registration_transform>`
     - Placed by
     - Posizionato da
     - ``places``
   * - :ref:`has_representation_model <edge-has_representation_model>`
     - Has representation model
     - Ha modello di rappresentazione
     - ``is_representation_model_of``
   * - :ref:`has_representation_model_doc <edge-has_representation_model_doc>`
     - Has document representation model
     - Ha modello di rappresentazione di documento
     - ``is_doc_representation_model_of``
   * - :ref:`has_representation_model_sf <edge-has_representation_model_sf>`
     - Has special find representation model
     - Ha modello di rappresentazione di reperto
     - ``is_sf_representation_model_of``
   * - :ref:`has_same_time <edge-has_same_time>`
     - Has same time
     - Contemporaneo a
     - —
   * - :ref:`has_semantic_shape <edge-has_semantic_shape>`
     - Has semantic shape
     - Ha forma semantica
     - ``is_semantic_shape_of``
   * - :ref:`has_sub_epoch <edge-has_sub_epoch>`
     - Has sub-epoch
     - Ha come sotto-epoca
     - ``is_in_epoch``
   * - :ref:`has_sub_resource <edge-has_sub_resource>`
     - Has sub-resource
     - Ha come parte l'insieme
     - ``is_sub_resource_of``
   * - :ref:`has_timebranch <edge-has_timebranch>`
     - Has timebranch
     - Ha il ramo temporale
     - ``is_timebranch_of``
   * - :ref:`has_translation <edge-has_translation>`
     - Has translation
     - Ha la traduzione
     - ``is_translation_of``
   * - :ref:`has_visual_reference <edge-has_visual_reference>`
     - Has visual reference
     - Ha riferimento visivo
     - ``is_visual_reference_of``
   * - :ref:`heritage_part_of <edge-heritage_part_of>`
     - Is part of heritage entity
     - Fa parte dell'entità patrimoniale
     - ``heritage_has_part``
   * - :ref:`includes_study <edge-includes_study>`
     - Includes study
     - Include lo studio
     - ``is_study_of_project``
   * - :ref:`is_after <edge-is_after>`
     - Is after
     - È posteriore a
     - ``is_before``
   * - :ref:`is_bonded_to <edge-is_bonded_to>`
     - Is bonded to
     - Si lega a
     - —
   * - :ref:`is_in_activity <edge-is_in_activity>`
     - Is in activity
     - È nell'attività
     - ``includes_in_activity``
   * - :ref:`is_in_district <edge-is_in_district>`
     - Is in district
     - È nel distretto
     - ``includes_in_district``
   * - :ref:`is_in_functional_unit <edge-is_in_functional_unit>`
     - Is in functional unit
     - È nell'unità funzionale
     - ``includes_in_functional_unit``
   * - :ref:`is_in_location <edge-is_in_location>`
     - Is in location
     - È nel luogo
     - ``includes_location``
   * - :ref:`is_in_paradata_nodegroup <edge-is_in_paradata_nodegroup>`
     - Is in paradata nodegroup
     - È nel gruppo di paradati
     - ``contains_paradata_node``
   * - :ref:`is_in_periodization <edge-is_in_periodization>`
     - Is in periodization
     - È nella periodizzazione
     - ``lists_horizon``
   * - :ref:`is_in_representation_model_group <edge-is_in_representation_model_group>`
     - Is in representation model group
     - È nel contenitore RM
     - ``includes_representation_model``
   * - :ref:`is_in_timebranch <edge-is_in_timebranch>`
     - Is in timebranch
     - È nel ramo temporale
     - ``contains_in_timebranch``
   * - :ref:`is_on_resource <edge-is_on_resource>`
     - Is on resource
     - Sta sulla risorsa
     - ``has_annotation_region``
   * - :ref:`is_part_of <edge-is_part_of>`
     - Is part of
     - Fa parte di
     - ``has_part``
   * - :ref:`is_physically_equal_to <edge-is_physically_equal_to>`
     - Is physically equal to
     - È fisicamente uguale a
     - —
   * - :ref:`overlies <edge-overlies>`
     - Overlies
     - Copre
     - ``is_overlain_by``
   * - :ref:`study_about_heritage <edge-study_about_heritage>`
     - Study is about heritage entity
     - Lo studio riguarda l'entità patrimoniale
     - ``was_subject_of_study``
   * - :ref:`study_produced_proposition_set <edge-study_produced_proposition_set>`
     - Study produced proposition set
     - Lo studio ha prodotto un insieme di proposizioni
     - ``was_created_by_study``
   * - :ref:`study_took_place_at <edge-study_took_place_at>`
     - Study took place at
     - Lo studio si è svolto in
     - ``was_place_of_study``
   * - :ref:`survive_in_epoch <edge-survive_in_epoch>`
     - Survives in epoch
     - Sopravvive nell'epoca
     - ``contains_surviving``
   * - :ref:`validated_by <edge-validated_by>`
     - Validated by
     - Validato da
     - ``validated``
   * - :ref:`was_revision_of <edge-was_revision_of>`
     - Was revision of
     - È una revisione di
     - ``had_revision``

.. toctree::
   :hidden:
   :glob:

   nodes/*
   edges/*

