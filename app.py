import streamlit as st
import networkx as nx
import requests
import time
from pyvis.network import Network
import os

# Set page config must be the first streamlit command
st.set_page_config(
    page_title="Actor Connection Finder",
    page_icon="🎬",
    layout="wide"
)

# Hardcoded API key (for development only)
TMDB_API_KEY = "b91a0fbde9fc501f2b98a260f47ccceb"  # Replace with your actual TMDB API key
# API base URL
BASE_URL = "https://api.tmdb.org/3"

# App title and description
st.title("🎬 Six Degrees of Hollywood")
st.subheader("Find connections between actors through their movie collaborations")

# Cache API requests to improve performance
@st.cache_data(ttl=3600)
def search_actor(name):
    """Search for an actor by name and return their ID and profile info"""
    url = f"{BASE_URL}/search/person"
    params = {
        "api_key": TMDB_API_KEY,
        "query": name,
        "language": "en-US",
        "include_adult": False
    }
    response = requests.get(url, params=params)
    data = response.json()
    
    if data["total_results"] > 0:
        return data["results"][0]
    return None

@st.cache_data(ttl=3600)
def get_actor_movies(actor_id):
    """Get movies an actor has appeared in"""
    url = f"{BASE_URL}/person/{actor_id}/movie_credits"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US"
    }
    response = requests.get(url, params=params)
    data = response.json()
    
    # Filter for cast only (not crew)
    return data.get("cast", [])

@st.cache_data(ttl=3600)
def get_movie_cast(movie_id):
    """Get the cast of a movie"""
    url = f"{BASE_URL}/movie/{movie_id}/credits"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US"
    }
    response = requests.get(url, params=params)
    data = response.json()
    
    return data.get("cast", [])

def build_actor_graph(start_actor_id, max_depth=2, max_movies_per_actor=5):
    """Build a graph of connected actors starting from a given actor"""
    G = nx.Graph()
    visited_actors = set()
    visited_movies = set()
    
    # Queue for BFS traversal: (actor_id, depth)
    queue = [(start_actor_id, 0)]
    
    with st.spinner("Building actor network..."):
        while queue:
            actor_id, depth = queue.pop(0)
            
            if actor_id in visited_actors:
                continue
                
            visited_actors.add(actor_id)
            
            # Stop if we've reached max depth
            if depth >= max_depth:
                continue
            
            # Get actor's movies
            movies = get_actor_movies(actor_id)
            
            # Sort by popularity and take top N
            movies = sorted(movies, key=lambda x: x.get("popularity", 0), reverse=True)[:max_movies_per_actor]
            
            for movie in movies:
                movie_id = movie["id"]
                movie_title = movie["title"]
                
                if movie_id in visited_movies:
                    continue
                    
                visited_movies.add(movie_id)
                
                # Get cast of the movie
                cast = get_movie_cast(movie_id)
                
                # Add edges between actors in this movie
                for cast_member in cast[:10]:  # Limit to top 10 cast members
                    cast_id = cast_member["id"]
                    cast_name = cast_member["name"]
                    
                    # Add actor node if not already in graph
                    if not G.has_node(cast_id):
                        profile_path = cast_member.get("profile_path")
                        image_url = f"https://image.tmdb.org/t/p/w185{profile_path}" if profile_path else ""
                        G.add_node(cast_id, name=cast_name, image=image_url)
                    
                    # Add edge with movie as relationship
                    if actor_id != cast_id:
                        if G.has_edge(actor_id, cast_id):
                            # Update edge with new movie
                            G[actor_id][cast_id]["movies"].append(movie_title)
                        else:
                            G.add_edge(actor_id, cast_id, movies=[movie_title])
                    
                    # Add new actors to queue
                    if cast_id not in visited_actors:
                        queue.append((cast_id, depth + 1))
    
    return G

def find_actor_connection(actor1_id, actor2_id):
    """Find the shortest path connecting two actors"""
    # Build graph starting from the first actor
    G = build_actor_graph(actor1_id, max_depth=2, max_movies_per_actor=5)
    
    # Check if the second actor is in the graph
    if not G.has_node(actor2_id):
        # If not, build graph from second actor and combine
        G2 = build_actor_graph(actor2_id, max_depth=2, max_movies_per_actor=5)
        G = nx.compose(G, G2)
    
    # Find shortest path if it exists
    try:
        path = nx.shortest_path(G, actor1_id, actor2_id)
        return G, path
    except nx.NetworkXNoPath:
        return G, None

def visualize_path(G, path):
    """Create a visualization of the connection path"""
    # Create a subgraph only containing the path
    if path:
        path_edges = [(path[i], path[i+1]) for i in range(len(path)-1)]
        path_graph = G.edge_subgraph(path_edges)
        
        # Create a PyVis network
        net = Network(height="600px", width="100%", bgcolor="#222222", font_color="white")
        
        # Add nodes and edges from the path
        for node in path:
            net.add_node(
                node, 
                label=G.nodes[node]["name"],
                title=G.nodes[node]["name"],
                image=G.nodes[node]["image"] if G.nodes[node]["image"] else None,
                shape="circularImage" if G.nodes[node]["image"] else "circle",
                size=30
            )
        
        for edge in path_edges:
            movies = G[edge[0]][edge[1]]["movies"]
            movie_titles = ", ".join(movies[:3])
            if len(movies) > 3:
                movie_titles += f" and {len(movies) - 3} more"
            net.add_edge(edge[0], edge[1], title=movie_titles)
        
        # Save and display the graph
        net.save_graph("actor_connection_graph.html")
        return "actor_connection_graph.html"
    return None

# User interface
with st.container():
    col1, col2 = st.columns(2)
    
    with col1:
        actor1_name = st.text_input("Enter first actor's name", "Tom Hanks")
    
    with col2:
        actor2_name = st.text_input("Enter second actor's name", "Kevin Bacon")

if st.button("Find Connection"):
    # Search for actors
    actor1 = search_actor(actor1_name)
    actor2 = search_actor(actor2_name)
    
    if not actor1:
        st.error(f"Could not find actor: {actor1_name}")
    elif not actor2:
        st.error(f"Could not find actor: {actor2_name}")
    else:
        # Display found actors
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader(actor1["name"])
            if actor1.get("profile_path"):
                st.image(f"https://image.tmdb.org/t/p/w185{actor1['profile_path']}")
        
        with col2:
            st.subheader(actor2["name"])
            if actor2.get("profile_path"):
                st.image(f"https://image.tmdb.org/t/p/w185{actor2['profile_path']}")
        
        # Find connection
        with st.spinner("Finding connection..."):
            G, path = find_actor_connection(actor1["id"], actor2["id"])
        
        if path:
            st.success(f"Found a connection with {len(path)-1} degrees of separation!")
            
            # Display path as text
            st.subheader("Connection Path:")
            
            for i in range(len(path)-1):
                current_actor = G.nodes[path[i]]["name"]
                next_actor = G.nodes[path[i+1]]["name"]
                movies = G[path[i]][path[i+1]]["movies"]
                
                st.write(f"{current_actor} → {next_actor} via '{movies[0]}'")
            
            # Display interactive graph
            graph_file = visualize_path(G, path)
            if graph_file:
                st.subheader("Interactive Visualization:")
                st.components.v1.html(open(graph_file, 'r', encoding='utf-8').read(), height=600)
        else:
            st.error(f"No connection found between {actor1['name']} and {actor2['name']} within the search depth.")
            st.info("Try increasing the search depth or choose different actors.")
            
            # Display stats about the graph
            st.write(f"Searched through {len(G.nodes)} actors and {len(G.edges)} connections.")

# Sidebar with additional information and settings
with st.sidebar:
    st.header("About")
    st.markdown("""
    This app uses data from The Movie Database (TMDB) to find connections between actors through their movie collaborations.
    
    The "six degrees of separation" theory suggests that any two actors can be connected through no more than six links.
    
    ### How it works:
    1. Enter two actor names
    2. The app searches for movies they've appeared in
    3. It builds a network of actors and their connections
    4. It finds the shortest path between the two actors
    
    ### Note:
    - The search is limited to a depth of 2 to keep the response time reasonable
    - Only the top 5 most popular movies per actor are considered
    """)
    
    st.header("Sample Connections")
    st.markdown("""
    Try these pairs:
    - Tom Hanks → Kevin Bacon
    - Meryl Streep → Brad Pitt  
    - Leonardo DiCaprio → Emma Stone
    """)
