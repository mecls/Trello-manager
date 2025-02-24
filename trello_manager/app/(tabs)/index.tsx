
import { ThemedText } from "@/components/ThemedText";
import React, { useState, useEffect } from "react";
import { View, TextInput, Button, Text, ScrollView, StyleSheet } from "react-native";
import { format, set } from "date-fns";

const MainScreen = () => {
  const [action, setAction] = useState("");
  const [answer, setAnswer] = useState("");
  const [boardResults, setBoardResults] = useState<any[]>([]);
  const [isVisible, setIsVisible] = useState(false);
  const [fieldsByCard, setfieldsByCard] = useState<any[]>([]);
  const [listByBoard, setListByBoard] = useState<{ [key: string]: any[] }>({});
  const [cardByList, setCardsByList] = useState<{ [key: string]: any[] }>({});

  // Fetch boards automatically when component mounts
  useEffect(() => {
    fetchBoards();
  }, []); // Runs when boardResults changes

  const act = async () => {
    try {
      const response = await fetch("http://127.0.0.1:8000/prompt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
  
      const data = await response.json();
      console.log("Response data:", data);  // Debugging
  
      setAnswer(data.answer || "No response from server.");
      setIsVisible(true);
      setAction("");
    } catch (error) {
      console.error("Error fetching AI response:", error);
      setAnswer("Error communicating with the server.");
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
          <View key={board.id} style={styles.boardCard}>
            <ThemedText type="subtitle">{board.name}</ThemedText>

            {/* Display Lists */}
            <ScrollView horizontal style={{ maxHeight: 200, marginTop: 10 }}>
              {listByBoard[board.id]?.length > 0 ? (
                listByBoard[board.id].map((list) => (
                  <View key={list.id} style={styles.listCard}>
                    <ThemedText type="defaultSemiBold">{list.name}</ThemedText>
                    {/* Display Cards for This List */}
                    <ScrollView>
                      {cardByList[list.id]?.length > 0 ? (
                        cardByList[list.id].map((card) => (
                          <View key={card.id} style={styles.cardBoard}>
                            <ThemedText type="default" style={{ fontWeight: '500' }}>{card.name}</ThemedText>
                            {card.desc && (
                              <ThemedText style={{ fontSize: 12 }}><ThemedText style={{ fontWeight: 'bold', fontSize: 12 }}>Desc: </ThemedText>{card.desc}</ThemedText>
                            )}
                            {card.due && (
                              <ThemedText style={{ fontSize: 12 }}>
                                <ThemedText style={{ fontWeight: 'bold', fontSize: 12 }}>Due: </ThemedText>
                                {format(new Date(card.due), "dd/MM/yyyy")}
                              </ThemedText>
                            )}
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
          value={action}
          onChangeText={setAction}
          placeholder="Ask a question..."
          style={styles.input}
        />
        <Button title="GO" onPress={act} />
      </View>

      {/* AI Answer & Clear Button */}
      <ScrollView style={{marginBottom:150}}>
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
    paddingTop: 80,
    paddingHorizontal: 15,
    // backgroundColor: "#f4f9fc", 
    //backgroundColor: "#faf0e6", 
    backgroundColor: "#fbf7f5",
  },
  centerText: {
    alignSelf: "center",
    fontWeight: "bold",
    marginBottom: 20,
    color: "#333", // Darker text for contrast
  },
  scrollContainer: {
    flexGrow: 2,
    paddingVertical: 10, // Adds spacing inside scroll
    gap: 15, // Ensures spacing between boards
  },
  boardCard: {
    padding: 15,
    marginTop: 10,
    width: 260,
    height: 300,
    backgroundColor: "#fff",
    marginHorizontal: 12,
    borderRadius: 15, // More rounded edges
    shadowColor: "#000",
    shadowOpacity: 0.08, // Softer shadow
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 6,
    elevation: 4,
  },
  listCard: {
    padding: 10,
    margin: 7,
    backgroundColor: "#dcf3ff", // Subtle blue background
    borderRadius: 12,
    width: 210,
    shadowColor: "#000",
    shadowOpacity: 0.1,
    shadowOffset: { width: 0, height: 1 },
    shadowRadius: 2,
    elevation: 3,
  },
  cardBoard: {
    padding: 8,
    marginTop: 12,
    borderRadius: 12,
    width: 190,
    borderColor: "#ff9a00",
    borderWidth: 1.5,
    backgroundColor: "#fff", // Ensure white background
    shadowColor: "#000",
    shadowOpacity: 0.08,
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 5,
    elevation: 3,
  },
  promptContainer: {
    flex: 8,
    marginTop: 10,
    alignItems: "center",
    paddingHorizontal: 20,
  },
  input: {
    borderWidth: 1,
    borderColor: "#ccc",
    padding: 12,
    width: "90%",
    borderRadius: 10,
    backgroundColor: "#fff",
    fontSize: 16,
    marginBottom: 10,
  },
  answerText: {
    marginTop: 0,
    fontWeight: "bold",
    fontSize: 16,
    color: "#333",
    textAlign: "center",
  },
});
