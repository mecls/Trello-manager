
import { ThemedText } from "@/components/ThemedText";
import React, { useState, useEffect } from "react";
import { View, TextInput, Button, Text, ScrollView, StyleSheet } from "react-native";

const MainScreen = () => {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [boardResults, setBoardResults] = useState<any[]>([]);
  const [isVisible, setIsVisible] = useState(false);
  const [cards, setCards] = useState<any[]>([]);
  const [listByBoard, setListByBoard] = useState<{ [key: string]: any[] }>({});
  const [cardByList, setCardsByList] = useState<{ [key: string]: any[] }>({});

  // Fetch boards automatically when component mounts
  useEffect(() => {
    fetchBoards();
  }, []); // Runs when boardResults changes


  // Fetch AI answer
  const askAI = async () => {
    try {
      const response = await fetch(`http://127.0.0.1:8000/ask?question=${encodeURIComponent(question)}`);
      const data = await response.json();
      setAnswer(data.answer);
      setIsVisible(true);
      setQuestion("");
    } catch (error) {
      console.error("Error fetching AI response:", error);
    }
  };

  const fetchBoards = async () => {
    try {
      const response = await fetch("http://127.0.0.1:8000/getBoards");
      const data = await response.json();

      if (data.boards) {
        setBoardResults(data.boards);

        // Fetch lists for each board after boards load
        data.boards.forEach((board: { id: any }) => {
          fetchListsForBoard(board.id);
        });
      } else {
        setBoardResults([]);
      }

      console.log("Fetched Boards:", data.boards);
    } catch (error) {
      console.error("Error fetching Trello boards:", error);
      setBoardResults([]);
    }
  };

  const fetchListsForBoard = async (boardId: any) => {
    try {
      const response = await fetch(`http://127.0.0.1:8000/getLists?board_id=${boardId}`);
      const data = await response.json();

      if (data.lists) {
        setListByBoard((prev) => ({
          ...prev,
          [boardId]: data.lists, // Ensure lists are properly categorized under each board
        }));
        // Fetch lists for each board after boards load
        data.lists.forEach((list: { id: any }) => {
          fetchCardbyList(list.id);
        });
      } else {
        setListByBoard((prev) => ({
          ...prev,
          [boardId]: [],
        }));
      }

      console.log(`Fetched Lists for Board ${boardId}:`, data.lists);
    } catch (error) {
      console.error("Error fetching Trello lists:", error);
      setListByBoard((prev) => ({
        ...prev,
        [boardId]: [],
      }));
    }
  };

  const fetchCardbyList = async (listId: any) => {
    try {
      const response = await fetch(`http://127.0.0.1:8000/getCards?list_id=${listId}`);
      const data = await response.json();

      if (data.cards) {
        setCardsByList((prev) => ({
          ...prev,
          [listId]: data.cards, // Ensure cards are properly categorized under each list
        }));

      } else {
        setCardsByList((prev) => ({
          ...prev,
          [listId]: [],
        }));
      }

    } catch (error) {
      console.error("Error fetching Trello cards:", error);
    }
  }

  return (
    <View style={styles.container}>
      {/* Display Boards */}
      <ThemedText type="title" style={styles.centerText}>Your Boards</ThemedText>
      <ScrollView horizontal contentContainerStyle={styles.scrollContainer} style={{ width: '100%' }}>
        {boardResults.map((board) => (
          <View key={board.id} style={[styles.boardCard]}>
            <ThemedText type="subtitle">{board.name}</ThemedText>

            {/* Display Lists */}
            <ScrollView horizontal style={{ maxHeight: 200, marginTop: 10 }}>
              {listByBoard[board.id]?.length > 0 ? (
                listByBoard[board.id].map((list) => (
                  <View key={list.id} style={{ padding: 5, margin: 5, backgroundColor: "#F4F4F4", borderRadius: 10, width: 200 }}>
                    <ThemedText type="defaultSemiBold">{list.name}</ThemedText>
                    {/* Display Cards for This List */}
                    <ScrollView>
                      {cardByList[list.id]?.length > 0 ? (
                        cardByList[list.id].map((card) => (
                          <View key={card.id} style={{ padding: 5, marginTop: 15, borderRadius: 10, width: 180, borderColor: "blue", borderWidth:1  }}>
                            <ThemedText type="default">{card.name}</ThemedText>
                          </View>
                        ))
                      ) : (
                        <ThemedText type="default">No cards</ThemedText>
                      )}
                    </ScrollView>

                  </View>
                ))
              ) : (
                <ThemedText type="default">No Lists</ThemedText>
              )}
            </ScrollView>
          </View>
        ))}
      </ScrollView>

      {/* Input Field & Button */}
      <View style={styles.promptContainer}>
        <ThemedText type="defaultSemiBold">Prompt an action:</ThemedText>
        <TextInput
          value={question}
          onChangeText={setQuestion}
          placeholder="Ask a question..."
          style={styles.input}
        />
        <Button title="OK" onPress={askAI} />
      </View>

      {/* AI Answer & Clear Button */}
      <ScrollView>
        {answer ? <Text style={styles.answerText}>Answer: {answer}</Text> : null}
        {isVisible && (
          <Button title="Clear" onPress={() => { setAnswer(""); setIsVisible(false); }} />
        )}
      </ScrollView>
    </View>
  );
};

export default MainScreen;


const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingTop: 90,
    margin: 10,
    alignContent: 'center',
    backgroundColor: "#f9f9f9",
  },
  centerText: {
    alignSelf: "center",
    fontWeight: "bold",
    marginBottom: 20,
  },
  scrollContainer: {
    flexGrow: 1,
    justifyContent: "flex-start",
  },
  boardCard: {
    padding: 10,
    marginTop: 10,
    width: 250,
    backgroundColor: "#fff",
    marginHorizontal: 10,
    borderRadius: 10,
    shadowColor: "#000",
    shadowOpacity: 0.1,
    shadowOffset: { width: 0, height: 3 },
    shadowRadius: 5,
    elevation: 3,
  },
  promptContainer: {
    marginTop: 20,
    alignItems: "center",
  },
  input: {
    borderWidth: 1,
    borderColor: "#ccc",
    padding: 10,
    width: 250,
    borderRadius: 8,
    marginBottom: 10,
  },
  answerText: {
    marginTop: 20,
    fontWeight: "bold",
  },
});
