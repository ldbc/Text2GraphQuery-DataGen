#Movie graph
#python ./examples/transform_schema_to_cpg.py --file example_schema --graph_name my_movie_graph --domain movie --subdomain movielens --csv_dir examples/generated_data/scripts/csv_files/ --control_dir examples/generated_controls/movie_graph/ --credentials pg/pg@cdb1_pdb1

# Geography graph
#python ./examples/transform_schema_to_cpg.py --file geography_schema --graph_name geography_graph --domain geography --subdomain cartography --csv_dir examples/generated_data/scripts/csv_files/geography/ --control_dir examples/generated_controls/geography_graph/ --credentials pg/pg@cdb1_pdb1

# Music graph
#python ./examples/transform_schema_to_cpg.py --file music_pop --graph_name music_graph --domain music --subdomain pop --csv_dir examples/generated_data/scripts/csv_files/music/ --control_dir examples/generated_controls/music_graph/ --credentials pg/pg@cdb1_pdb1

# Animals graph
python ./examples/generate_oracle_graph.py --graph_name animals_graph --domain nature --subdomain animals --csv_dir examples/generated_data/scripts/csv_files/animals --control_dir examples/generated_controls/animals_graph/ --credentials pg/pg@cdb1_pdb1
