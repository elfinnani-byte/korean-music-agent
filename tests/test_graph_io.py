import networkx as nx
import graph_io


def _sample():
    g = nx.MultiDiGraph()
    g.add_node("artist:양현석", name="양현석", type="Artist",
               norm="양현석", aliases=["YG 양현석"], degree=2, is_hub=False)
    g.add_node("label:yg", name="YG 엔터테인먼트", type="Label",
               norm="yg엔터테인먼트", aliases=[], degree=1, is_hub=False)
    g.add_edge("artist:양현석", "label:yg", relation="FOUNDED",
               props={"year": 1996}, origins=["llm"], agreement=0.8, count=1,
               sources=["양현석.md"], quotes=["1996년 YG 엔터테인먼트를 설립하였다."])
    return g


def test_json_round_trip_preserves_everything(tmp_path):
    g = _sample()
    p = tmp_path / "graph.json"
    graph_io.write_json(g, p)
    back = graph_io.read_json(p)
    assert back.number_of_nodes() == g.number_of_nodes()
    assert back.number_of_edges() == g.number_of_edges()
    e = list(back.edges(data=True))[0][2]
    assert e["quotes"] == ["1996년 YG 엔터테인먼트를 설립하였다."]
    assert e["props"]["year"] == 1996


def test_graphml_round_trip_keeps_counts_and_korean(tmp_path):
    """networkx 의 graphml writer 는 리스트·dict·None 을 저장하지 못한다.
       저장이 됐다는 것과 제대로 됐다는 것은 다르다."""
    g = _sample()
    p = tmp_path / "graph.graphml"
    graph_io.write_graphml(g, p)
    back = nx.read_graphml(p)
    assert back.number_of_nodes() == g.number_of_nodes()
    assert back.number_of_edges() == g.number_of_edges()
    names = {d["name"] for _, d in back.nodes(data=True)}
    assert "YG 엔터테인먼트" in names


def test_graphml_joins_list_attributes(tmp_path):
    g = _sample()
    g.add_edge("artist:양현석", "label:yg", relation="SIGNED_TO",
               props={}, origins=["rule", "llm"], agreement=1.0, count=2,
               sources=["a.md", "b.md"], quotes=["q1", "q2"])
    p = tmp_path / "graph.graphml"
    graph_io.write_graphml(g, p)
    back = nx.read_graphml(p)
    joined = [d["sources"] for _, _, d in back.edges(data=True)]
    assert any("|" in s for s in joined)


def test_graphml_omits_none_instead_of_writing_empty_string(tmp_path):
    g = _sample()
    g.add_node("song:x:_", name="X", type="Song", norm="x", aliases=[],
               degree=0, is_hub=False, year=None)
    p = tmp_path / "graph.graphml"
    graph_io.write_graphml(g, p)
    back = nx.read_graphml(p)
    assert "year" not in back.nodes["song:x:_"]
